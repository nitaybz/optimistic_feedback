DOMAIN = "optimistic_feedback"
CONF_DOMAINS = "domains"
CONF_EXCLUDE = "exclude_entities"
CONF_INCLUDE_MODE = "include_mode"
CONF_SELECTED_ENTITIES = "selected_entities"
CONF_DEBOUNCE_TIME = "debounce_time"

DEFAULT_DOMAINS = ["light", "switch"]
ALL_SUPPORTED_DOMAINS = ["light", "switch", "cover", "fan", "climate", "media_player", "lock"]
DEFAULT_DEBOUNCE_MS = 400
EVENT_CALL_SERVICE = "call_service"

# Maps service name → optimistic state string
SERVICE_MAP = {
    # Basic on/off services
    "turn_on": "on",
    "turn_off": "off",
    # Cover services
    "open_cover": "open",
    "close_cover": "closed",
    "set_cover_position": "open",  # best effort
    "stop_cover": "stopped",
    # Media player services  
    "media_play": "playing",
    "media_pause": "paused",
    "media_stop": "idle",
    # Lock services
    "lock": "locked",
    "unlock": "unlocked",
    # Generic toggle
    "toggle": "on",  # assume success, will be refined by domain logic
}
