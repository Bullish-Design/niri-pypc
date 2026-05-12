"""Protocol types for niri IPC."""

from niri_pypc.types.base import (
    ExternallyTaggedEnum,
    ProtocolModel,
    ProtocolVariant,
    UnknownEvent,
)
from niri_pypc.types.codec import decode_externally_tagged as decode_externally_tagged
from niri_pypc.types.codec import encode_externally_tagged as encode_externally_tagged
from niri_pypc.types.codec import unwrap_reply as unwrap_reply
from niri_pypc.types.generated import *  # noqa: F401,F403
