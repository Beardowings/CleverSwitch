import dataclasses

DEFAULT_BUTTON_CID = 0x00C3  # MX Master thumb (gesture) button


@dataclasses.dataclass(frozen=True)
class MouseButtonSwitchConfig:
    enabled: bool = False
    cid: int = DEFAULT_BUTTON_CID
    target_host: int = 1  # 0-based
    divert: bool = True  # False: only listen, for when a peer app (Logi Options+) already diverts the button
