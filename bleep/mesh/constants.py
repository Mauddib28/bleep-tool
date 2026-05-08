"""Bluetooth Mesh D-Bus constants derived from BlueZ ``mesh-api.txt``.

Reference: ``workDir/bluez/doc/mesh-api.txt`` (BlueZ 5.66+).

All daemon-side interfaces live under the ``org.bluez.mesh`` well-known name.
Application-side interfaces (Application1, Element1, Provisioner1,
ProvisionAgent1) are implemented by the caller on its own bus name.
"""

# Well-known D-Bus service name for bluetooth-meshd
MESH_SERVICE = "org.bluez.mesh"

# Root object path where Network1 is exported
MESH_ROOT_PATH = "/org/bluez/mesh"

# Node object path template: /org/bluez/mesh/node<uuid>
# <uuid> is the 32-hex-char device UUID (no dashes, lowercase)
MESH_NODE_PATH_PREFIX = "/org/bluez/mesh/node"

# ---------------------------------------------------------------------------
# Daemon-side interfaces (client calls into bluetooth-meshd)
# ---------------------------------------------------------------------------
MESH_NETWORK_IFACE = "org.bluez.mesh.Network1"
MESH_NODE_IFACE = "org.bluez.mesh.Node1"
MESH_MANAGEMENT_IFACE = "org.bluez.mesh.Management1"

# ---------------------------------------------------------------------------
# Application-side interfaces (bluetooth-meshd calls into the app)
# ---------------------------------------------------------------------------
MESH_APPLICATION_IFACE = "org.bluez.mesh.Application1"
MESH_ELEMENT_IFACE = "org.bluez.mesh.Element1"
MESH_PROVISIONER_IFACE = "org.bluez.mesh.Provisioner1"
MESH_PROVISION_AGENT_IFACE = "org.bluez.mesh.ProvisionAgent1"
MESH_ATTENTION_IFACE = "org.bluez.mesh.Attention1"

# ---------------------------------------------------------------------------
# Error domain — org.bluez.mesh.Error.*
# ---------------------------------------------------------------------------
MESH_ERROR_PREFIX = "org.bluez.mesh.Error"
MESH_ERROR_INVALID_ARGS = f"{MESH_ERROR_PREFIX}.InvalidArguments"
MESH_ERROR_ALREADY_EXISTS = f"{MESH_ERROR_PREFIX}.AlreadyExists"
MESH_ERROR_NOT_FOUND = f"{MESH_ERROR_PREFIX}.NotFound"
MESH_ERROR_BUSY = f"{MESH_ERROR_PREFIX}.Busy"
MESH_ERROR_FAILED = f"{MESH_ERROR_PREFIX}.Failed"
MESH_ERROR_NOT_AUTHORIZED = f"{MESH_ERROR_PREFIX}.NotAuthorized"
MESH_ERROR_DOES_NOT_EXIST = f"{MESH_ERROR_PREFIX}.DoesNotExist"
MESH_ERROR_NOT_SUPPORTED = f"{MESH_ERROR_PREFIX}.NotSupported"
MESH_ERROR_IN_PROGRESS = f"{MESH_ERROR_PREFIX}.InProgress"
MESH_ERROR_ABORT = f"{MESH_ERROR_PREFIX}.Abort"

# ---------------------------------------------------------------------------
# Default application paths used by BLEEP's mesh helpers
# ---------------------------------------------------------------------------
BLEEP_MESH_APP_ROOT = "/bleep/mesh/app"
BLEEP_MESH_ELEMENT_PREFIX = "/bleep/mesh/app/ele"
BLEEP_MESH_AGENT_PATH = "/bleep/mesh/agent"
