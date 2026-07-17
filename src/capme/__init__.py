"""CAP-ME research benchmark.

The package intentionally models controlled synthetic workloads. It is not a
production circumvention service and does not contact third-party systems.
"""

from .model import ARCHITECTURES, CENSOR_REGIMES, NETWORKS, WORKLOADS

__all__ = ["ARCHITECTURES", "CENSOR_REGIMES", "NETWORKS", "WORKLOADS"]
__version__ = "0.3.0"
