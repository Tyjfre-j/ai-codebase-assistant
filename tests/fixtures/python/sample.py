import os
from dataclasses import dataclass


@dataclass
class Point:
    x: int
    y: int


class ShapeCalculator:
    """Computes areas for a small set of shapes."""

    unit: str = "cm"

    def __init__(self, precision: int = 2):
        self.precision = precision

    def circle_area(self, radius: float) -> float:
        return round(3.14159 * radius * radius, self.precision)

    @staticmethod
    def square_area(side: float) -> float:
        return side * side

    def rectangle_area(self, width: float, height: float) -> float:
        def _validate(n):
            if n < 0:
                raise ValueError("negative dimension")
        _validate(width)
        _validate(height)
        return width * height


def standalone_helper(path: str) -> bool:
    return os.path.exists(path)