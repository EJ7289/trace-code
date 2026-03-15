"""Abstract base parser interface."""

from abc import ABC, abstractmethod
from typing import List
from ..graph import FunctionNode


class BaseParser(ABC):
    """Parse a source file and return a list of FunctionNode objects."""

    @abstractmethod
    def parse(self, file_path: str) -> List[FunctionNode]:
        """
        Parse the file at `file_path` and extract all function definitions
        along with the list of function calls each one makes.

        Returns a list of FunctionNode instances.
        """
        raise NotImplementedError
