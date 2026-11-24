// Fixed Keychain service/accounts. Credentials are accepted only over standard input.
import Foundation
import Security

let accounts: Set<String> = ["google.client", "google.calendar", "google.gmail", "github.pages"]
let service = "local.june.integrations.v1"

func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
        FileHandle.standardOutput.write(data)
    }
}

func valid(_ request: [String: Any]) -> Bool {
    guard let account = request["account"] as? String, accounts.contains(account),
          let operation = request["operation"] as? String else { return false }
    let keys = Set(request.keys)
    if operation == "put" {
        guard keys == ["operation", "account", "secret"], let secret = request["secret"] as? String else { return false }
        return !secret.isEmpty && secret.utf8.count <= 16384
    }
    return (operation == "get" || operation == "delete") && keys == ["operation", "account"]
}

if CommandLine.arguments == [CommandLine.arguments[0], "--self-test"] {
    let okay = valid(["operation": "get", "account": "google.calendar"])
        && !valid(["operation": "get", "account": "other"])
        && !valid(["operation": "put", "account": "google.calendar", "secret": ""])
        && !valid(["operation": "get", "account": "google.calendar", "extra": true])
    emit(["ok": okay]); exit(okay ? 0 : 1)
}

guard CommandLine.arguments.count == 1,
      let data = try? FileHandle.standardInput.read(upToCount: 65537), data.count <= 65536,
      let request = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], valid(request),
      let account = request["account"] as? String,
      let operation = request["operation"] as? String else {
    emit(["ok": false]); exit(1)
}

let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: service, kSecAttrAccount as String: account,
    kSecAttrSynchronizable as String: false]
var status: OSStatus = errSecParam
if operation == "put", let secret = request["secret"] as? String {
    let attributes: [String: Any] = [kSecValueData as String: Data(secret.utf8)]
    status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
    if status == errSecItemNotFound {
        var item = query
        item[kSecValueData as String] = Data(secret.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        status = SecItemAdd(item as CFDictionary, nil)
    }
} else if operation == "delete" {
    status = SecItemDelete(query as CFDictionary)
    if status == errSecItemNotFound { status = errSecSuccess }
} else if operation == "get" {
    var lookup = query
    lookup[kSecReturnData as String] = true
    lookup[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    status = SecItemCopyMatching(lookup as CFDictionary, &result)
    if status == errSecItemNotFound { emit(["ok": true]); exit(0) }
    if status == errSecSuccess, let bytes = result as? Data,
       let secret = String(data: bytes, encoding: .utf8) {
        emit(["ok": true, "secret": secret]); exit(0)
    }
    emit(["ok": false]); exit(1)
}
emit(["ok": status == errSecSuccess])
exit(status == errSecSuccess ? 0 : 1)
