from pulseguard.models.adapters import CarrierConfig

CARRIER_CONFIGS: dict[str, CarrierConfig] = {
    "verizon": CarrierConfig(
        name="verizon",
        display_name="Verizon",
        handles=["@Verizon", "@VerizonSupport", "@VZWSupport"],
        keywords=["verizon", "vzw", "verizonwireless"],
        subreddits=["verizon"],
    ),
    "tmobile": CarrierConfig(
        name="tmobile",
        display_name="T-Mobile",
        handles=["@TMobile", "@TMobileHelp"],
        keywords=["t-mobile", "tmobile", "tmo"],
        subreddits=["tmobile"],
    ),
    "att": CarrierConfig(
        name="att",
        display_name="AT&T",
        handles=["@ATT", "@ATTHelp", "@ATTBusiness"],
        keywords=["at&t", "att", "attwireless"],
        subreddits=["ATT"],
    ),
}


def get_carrier_config(name: str) -> CarrierConfig | None:
    return CARRIER_CONFIGS.get(name.lower())


def detect_carrier(text: str) -> str | None:
    text_lower = text.lower()
    for carrier, config in CARRIER_CONFIGS.items():
        for keyword in config.keywords:
            if keyword.lower() in text_lower:
                return carrier
        for handle in config.handles:
            if handle.lower() in text_lower:
                return carrier
    return None
