import dataclasses

DEFAULT_BUTTON_CID = 0x00C3  # MX Master thumb (gesture) button


@dataclasses.dataclass(frozen=True)
class MouseButtonSwitchConfig:
    enabled: bool = False
    cid: int = DEFAULT_BUTTON_CID
    target_host: int | None = None  # 0-based; None until a host is chosen (a press then switches nothing)
    divert: bool = True  # False: only listen, for when a peer app (Logi Options+) already diverts the button
    follow_keyboard: bool = False  # the mouse follows a keyboard that leaves by its own Easy-Switch key

    @property
    def armed(self) -> bool:
        """Whether the button should be diverted on the mouse right now."""
        return self.enabled and self.divert
