// Protocol 1 is private stdin/stdout IPC, never a listening server. The reader
// owns stdin and cancellation; the main thread alone owns the Whisper context.
#include "whisper.h"
#include "json.hpp" // Pinned whisper.cpp examples header; no fetched dependency.
#include <algorithm>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::ordered_json;
constexpr size_t MAX_COMMAND = 4096, MAX_AUDIO = 1048576, MAX_REPLY = 65536;
std::mutex output_mutex;

void emit(const json & value) {
    std::lock_guard<std::mutex> guard(output_mutex);
    const auto encoded = value.dump(-1, ' ', false, json::error_handler_t::replace);
    if (encoded.size() + 1 > MAX_REPLY) std::exit(3);
    std::cout << encoded << '\n' << std::flush;
    if (!std::cout) std::exit(0); // Parent pipe disappeared; no orphan compute.
}
void error(const std::string & id, const char * code) {
    emit({{"type", "error"}, {"id", id}, {"code", code}});
}

bool valid_id(const std::string & id) {
    if (id.empty() || id.size() > 64) return false;
    return std::all_of(id.begin(), id.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
               (c >= '0' && c <= '9') || c == '-' || c == '_';
    });
}
uint32_t u32(const std::vector<uint8_t> & b, size_t i) {
    return uint32_t(b[i]) | (uint32_t(b[i+1]) << 8) |
           (uint32_t(b[i+2]) << 16) | (uint32_t(b[i+3]) << 24);
}
uint16_t u16(const std::vector<uint8_t> & b, size_t i) {
    return uint16_t(b[i]) | (uint16_t(b[i+1]) << 8);
}
bool decode_wav(const std::vector<uint8_t> & b, std::vector<float> & samples) {
    if (b.size() < 44 || b.size() > MAX_AUDIO || std::memcmp(b.data(), "RIFF", 4) ||
        std::memcmp(b.data()+8, "WAVEfmt ", 8) || std::memcmp(b.data()+36, "data", 4) ||
        u32(b,4) != b.size()-8 || u32(b,16) != 16 || u16(b,20) != 1 ||
        u16(b,22) != 1 || u32(b,24) != 16000 || u32(b,28) != 32000 ||
        u16(b,32) != 2 || u16(b,34) != 16 || u32(b,40) != b.size()-44 ||
        (b.size()-44)%2 || b.size()-44 < 16000 || b.size()-44 > 960000) return false;
    samples.reserve((b.size()-44)/2);
    for (size_t i=44; i<b.size(); i+=2) {
        int sample = u16(b,i);
        if (sample >= 32768) sample -= 65536;
        samples.push_back(float(sample)/32768.f);
    }
    return true;
}

struct State {
    std::mutex mutex;
    std::condition_variable changed;
    std::string id;
    std::vector<float> samples;
    bool pending = false, stopping = false, protocol_error = false;
    std::atomic<bool> cancelled{false};
};

// Bounded reads deliberately avoid getline, which can allocate an arbitrary
// amount before it returns. An invalid header is fatal: framing cannot be trusted.
void control(State & state) {
    try {
        while (true) {
            std::string line;
            char c;
            bool complete = false;
            while (std::cin.get(c)) {
                if (c == '\n') { complete = true; break; }
                if (line.size() >= MAX_COMMAND-1) throw std::runtime_error("protocol");
                line.push_back(c);
            }
            if (!complete) {
                if (!line.empty()) throw std::runtime_error("protocol");
                break;
            }
            const auto command = json::parse(line);
            const auto type = command.at("type").get<std::string>();
            const auto id = command.at("id").get<std::string>();
            if (!valid_id(id)) throw std::runtime_error("protocol");
            if (type == "cancel") {
                std::lock_guard<std::mutex> guard(state.mutex);
                if (state.id == id) state.cancelled.store(true);
                else emit({{"type", "cancel-ignored"}, {"id", id}});
            } else if (type == "transcribe") {
                const auto & size_value = command.at("bytes");
                if (!size_value.is_number_unsigned() && !size_value.is_number_integer()) throw std::runtime_error("protocol");
                const auto size = size_value.get<int64_t>();
                if (size < 44 || size > int64_t(MAX_AUDIO)) throw std::runtime_error("protocol");
                std::vector<uint8_t> bytes(size);
                if (!std::cin.read(reinterpret_cast<char *>(bytes.data()), size)) break;
                std::vector<float> samples;
                if (!decode_wav(bytes, samples)) { error(id, "invalid-audio"); continue; }
                std::lock_guard<std::mutex> guard(state.mutex);
                if (!state.id.empty()) { error(id, "busy"); continue; }
                state.id = id;
                state.samples = std::move(samples);
                state.cancelled.store(false);
                state.pending = true;
                state.changed.notify_one();
            } else throw std::runtime_error("protocol");
        }
    } catch (...) {
        error("", "protocol");
        std::lock_guard<std::mutex> guard(state.mutex);
        state.protocol_error = true;
    }
    {
        std::lock_guard<std::mutex> guard(state.mutex);
        state.stopping = true;
        state.cancelled.store(true);
    }
    state.changed.notify_one();
}

bool abort_compute(void * opaque) {
    return static_cast<State *>(opaque)->cancelled.load();
}
void quiet_log(ggml_log_level, const char *, void *) {} // Never log audio/text.

json infer(whisper_context * context, State & state, const std::string & id,
           const std::vector<float> & samples) {
    auto params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
    // The greedy candidate failed the exact-name acceptance gate. Keep the
    // established decoder while retaining resident model and cancellation.
    params.n_threads = 2;
    params.greedy.best_of = 5;
    params.beam_search.beam_size = 5;
    params.temperature = 0;
    params.temperature_inc = .2f; // Established fallback; fast decoder withheld.
    params.language = "en";
    params.no_context = true; // No cross-job prompts or transcript conditioning.
    params.no_timestamps = true;
    params.print_special = false;
    params.print_progress = false;
    params.print_realtime = false;
    params.print_timestamps = false;
    params.suppress_nst = true;
    params.abort_callback = abort_compute;
    params.abort_callback_user_data = &state;
    const int code = whisper_full(context, params, samples.data(), int(samples.size()));
    if (state.cancelled.load()) return {{"type", "cancelled"}, {"id", id}};
    if (code != 0) return {{"type", "error"}, {"id", id}, {"code", "engine-failed"}};
    std::string text;
    double log_probability = 0, no_speech = 0;
    size_t tokens = 0;
    const int segments = whisper_full_n_segments(context);
    for (int segment=0; segment<segments; ++segment) {
        const char * part = whisper_full_get_segment_text(context, segment);
        if (part) { if (!text.empty()) text += ' '; text += part; }
        if (text.size() > 16000) return {{"type", "error"}, {"id", id}, {"code", "result-too-large"}};
        // Conservative aggregation: reject if any returned segment looks silent.
        no_speech = std::max(no_speech, double(whisper_full_get_segment_no_speech_prob(context, segment)));
        for (int token=0; token<whisper_full_n_tokens(context, segment); ++token) {
            const auto data = whisper_full_get_token_data(context, segment, token);
            if (data.id >= whisper_token_eot(context)) continue;
            log_probability += std::log(std::max(1e-9, double(data.p)));
            ++tokens;
        }
    }
    return {{"type", "result"}, {"id", id}, {"text", text},
            {"confidence", tokens ? std::exp(log_probability/tokens) : 0.0},
            {"noSpeechProbability", segments ? no_speech : 1.0}};
}

int main(int argc, char ** argv) {
    if (argc != 3 || std::string(argv[1]) != "--model") return 2;
    whisper_log_set(quiet_log, nullptr);
    auto params = whisper_context_default_params();
    params.use_gpu = false;
    params.flash_attn = false;
    std::unique_ptr<whisper_context, decltype(&whisper_free)> context(
        whisper_init_from_file_with_params(argv[2], params), whisper_free);
    if (!context) { error("", "model-load-failed"); return 2; }
    emit({{"type", "ready"}, {"protocol", 1}, {"model", "base.en"}});
    State state;
    std::thread reader(control, std::ref(state));
    while (true) {
        std::unique_lock<std::mutex> guard(state.mutex);
        state.changed.wait(guard, [&] { return state.pending || state.stopping; });
        if (state.stopping) break;
        const auto id = state.id;
        auto samples = std::move(state.samples);
        state.pending = false;
        guard.unlock();
        json result;
        try { result = infer(context.get(), state, id, samples); }
        catch (...) { result = {{"type", "error"}, {"id", id}, {"code", "engine-failed"}}; }
        guard.lock();
        // Serialize completion with cancel/new-job acceptance. A cancel that
        // wins the race suppresses text even if the final decoder just finished.
        if (state.cancelled.load()) result = {{"type", "cancelled"}, {"id", id}};
        if (!state.stopping) emit(result);
        state.id.clear();
    }
    reader.join();
    return state.protocol_error ? 2 : 0;
}
