"""Verified local product facts. An exact model match prevents variant mixups."""
import re


MSI_X870E = re.compile(r'\bx870e\s+gaming\s+plus\s+wi[\s-]?fi\b(?!\s+max\b)', re.I)
CONTEXT_REFERENCE = re.compile(r'^\s*(?:like\b|(?:and\s+)?what about\b)|\b(?:it|its|their|this motherboard|that motherboard|the motherboard)\b', re.I)
OTHER_PRODUCT = re.compile(r'\b(?:asrock|asus|gigabyte|biostar|x870|x670e?|b850|b650e?|max wifi)\b', re.I)
COMPARISON = re.compile(r'\b(?:compare|versus|vs|difference|better)\b', re.I)
BUILD_PAIR = re.compile(r'\b(?:both|either|(?:these|the|my) two)\s+(?:pc\s+)?builds?\b', re.I)
RYZEN_9800X3D = re.compile(r'\bryzen\s+7\s+9800x3d\b', re.I)
BOARD_ADVICE = re.compile(
    r'\b(?:keep|switch|replace|upgrade|recommend\w*|alternatives?|better|enough|overkill|worth)\b', re.I,
)

MSI_REFERENCE = '''Manufacturer reference · MSI X870E Gaming Plus WiFi

• Platform: ATX (305 × 244 mm), AMD X870E chipset and AM5 socket for Ryzen 7000, 8000 and 9000 desktop CPUs.
• Memory: four DDR5 UDIMM slots, up to 256 GB, dual channel and AMD EXPO. MSI lists up to 8200+ MT/s with overclocking. Actual speeds depend on the CPU and DIMM layout.
• PCIe: four physical slots, three x16-length and one x1. E1 is PCIe 5.0 ×16 with Ryzen 7000/9000. E3 is PCIe 4.0 ×4 electrically. E2 and E4 are PCIe 3.0 ×1 electrically. Ryzen 8000 CPUs reduce E1 to Gen4 ×8 or ×4 depending on model.
• Storage: three SSD M.2 slots and four SATA 6 Gb/s ports. M.2_1 is up to Gen5 ×4 with 7000/9000 (2260/2280), or Gen4 ×4 with Ryzen 8000. M.2_2 is Gen4 ×4 (2260/2280) and M.2_3 is Gen4 ×4 (2280/22110). NVMe RAID 0/1/5, with RAID 5 limited to Ryzen 9000. SATA RAID 0/1/10.
• Networking: built-in Wi-Fi 7, Bluetooth 5.4 and Realtek 5 Gb Ethernet. The Wi-Fi module uses a separate Key-E slot. Availability of 6 GHz and wireless features depends on your region, OS and network equipment.
• USB and display: rear USB4 40 Gb/s Type-C, one 20 Gb/s Type-C, two 10 Gb/s Type-A, two 5 Gb/s Type-A and four USB 2.0. Front headers provide one 10 Gb/s Type-C, four 5 Gb/s Type-A and six USB 2.0. HDMI 2.1 and USB4 display output require CPU graphics. Audio is Realtek ALC897 with 7.1-channel support.
• BIOS and tuning: MSI Click BIOS X with EZ and Advanced views, M-Flash, rear Flash BIOS and Clear CMOS buttons, and hardware monitoring. MSI lists Game Boost, PBO presets, Performance Switch, PBO thermal targets of 65/75/85 °C and EXPO/A-XMP memory profiles. AMD Precision Boost 2 handles automatic CPU boosting. PBO and Game Boost are optional tuning controls. Available settings vary with CPU and firmware. Check the BIOS screen for the installed version.
• Board controls: 14+2+1 power design, two CPU power connectors, one CPU fan header, one pump/system fan header, six system fan headers, debug LEDs and RGB/ARGB headers.

MSI specifications: https://www.msi.com/Motherboard/X870E-GAMING-PLUS-WIFI/Specification
MSI BIOS and tuning overview: https://www.msi.com/Motherboard/X870E-GAMING-PLUS-WIFI
MSI BIOS downloads: https://www.msi.com/Motherboard/X870E-GAMING-PLUS-WIFI/support
AMD automatic CPU boost: https://www.amd.com/en/resources/support-articles/faqs/cpu-pb2.html'''


def motherboard_reference(question, subject=''):
    if COMPARISON.search(question):
        return ''
    if MSI_X870E.search(question) or (not OTHER_PRODUCT.search(question) and CONTEXT_REFERENCE.search(question) and MSI_X870E.search(subject)):
        return MSI_REFERENCE
    return ''


def motherboard_build_advice(question, citations):
    """Only advise on the known pair when both live quotes establish the parts."""
    pair = BUILD_PAIR.search(question)
    if not pair or not BOARD_ADVICE.search(question):
        return ''
    # This default advice is for a plain keep-or-replace question. It does
    # not answer added requirements about devices, budgets, or other models.
    if not re.fullmatch(
        r'\s*(?:[,;]?\s*(?:or\s+)?(?:(?:is|are)\s+(?:these|they|it|this)|'
        r'(?:these|they|it|this)\s+(?:is|are))\s+enough)?\s*[?.!]*\s*',
        question[pair.end():], re.I,
    ):
        return ''
    if OTHER_PRODUCT.search(question) or re.search(r'\b(?:versus|vs|compare)\b', question, re.I):
        return ''
    if len({c['documentId'] for c in citations}) != 2 or not all(
        not c.get('deleted') and MSI_X870E.search(c['quote']) and RYZEN_9800X3D.search(c['quote'])
        for c in citations
    ):
        return ''
    return (
        'Recommendation\n'
        'Keep the MSI X870E Gaming Plus WiFi for either build unless you can save money on a board '
        'with the ports and storage you need. Both quotes pair it with a Ryzen 7 9800X3D. '
        'With that CPU the main slot runs at PCIe 5.0 ×16, so either build’s single graphics card '
        'has the slot it needs. I wouldn’t pay more for a motherboard just to switch GPUs.\n\n'
        'If the MSI MAG B850 Tomahawk Max WiFi is meaningfully cheaper, it’s a good alternative. '
        'It retains the main PCIe 5.0 ×16 slot, Wi-Fi 7 and 5 Gb Ethernet, and offers four SSD M.2 slots '
        'instead of three. Its third M.2 slot shares bandwidth with a lower PCIe slot. '
        'Keep the X870E if you need its rear 40 Gb/s USB4 port. Check the current price before deciding.\n\n'
        'MSI X870E specifications: https://www.msi.com/Motherboard/X870E-GAMING-PLUS-WIFI/Specification\n'
        'MSI B850 specifications: https://www.msi.com/Motherboard/MAG-B850-TOMAHAWK-MAX-WIFI/Specification'
    )
