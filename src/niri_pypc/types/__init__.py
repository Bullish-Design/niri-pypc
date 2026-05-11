"""Protocol types for niri IPC."""

from niri_pypc.types.generated import *  # noqa: F401,F403
from niri_pypc.types.codec import (
    decode_externally_tagged,
    encode_externally_tagged,
    unwrap_reply,
)
