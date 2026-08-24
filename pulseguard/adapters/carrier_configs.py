from pulseguard.models.adapters import CarrierConfig

CARRIER_CONFIGS: dict[str, CarrierConfig] = {
    "verizon": CarrierConfig(
        name="verizon",
        display_name="Verizon",
        handles=["@Verizon", "@VerizonSupport", "@VZWSupport"],
        keywords=["verizon", "vzw", "verizonwireless"],
        app_store_id="1489157249",
        play_store_id="com.verizon.mymobilesecure",
        trustpilot_slug="verizon",
        subreddits=["verizon"],
    ),
    "tmobile": CarrierConfig(
        name="tmobile",
        display_name="T-Mobile",
        handles=["@TMobile", "@TMobileHelp"],
        keywords=["t-mobile", "tmobile", "tmo"],
        app_store_id="561625752",
        play_store_id="com.tmobile.pr.mytmobile",
        trustpilot_slug="t-mobile",
        subreddits=["tmobile"],
    ),
    "att": CarrierConfig(
        name="att",
        display_name="AT&T",
        handles=["@ATT", "@ATTHelp", "@ATTBusiness"],
        keywords=["at&t", "att", "attwireless"],
        app_store_id="306862109",
        play_store_id="com.att.myWireless",
        trustpilot_slug="att",
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
