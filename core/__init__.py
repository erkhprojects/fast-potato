from core.app import FastPotato
from core.depends import Depends, PotatoDepends
from core.potato import Potato
from core.protocols import TaskProtocol
from core.resolver import DependencyResolver

__all__ = ["Depends", "DependencyResolver", "FastPotato", "Potato", "PotatoDepends", "TaskProtocol"]

