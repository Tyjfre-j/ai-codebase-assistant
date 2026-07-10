import { readFile } from "fs";

class ShapeCalculator {
  constructor(precision = 2) {
    this.precision = precision;
  }

  circleArea(radius) {
    return Math.round(Math.PI * radius * radius * 100) / 100;
  }

  squareArea = (side) => {
    return side * side;
  };
}

const helpers = {
  double(n) {
    return n * 2;
  },
};

function standaloneHelper(path) {
  return path.length > 0;
}