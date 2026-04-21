"""
Lane-detection helper for centering the car in a lane.

Mirrors the shape of the servo / esc helpers: a class you can import and
reuse from cmd_mux (or any control loop), plus a `main()` that runs it
standalone and shows the camera feed in real time.

Run as a standalone tester (Windows / WSL / Linux):
    uv run python -m helpers.vision_serial
    uv run python -m helpers.vision_serial --camera 1
"""

import argparse
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class LaneResult:
    # diff > 0 -> lane center is right of the image center (steer right)
    # diff < 0 -> lane center is left  of the image center (steer left)
    # bias in [-1, 1], normalized version of diff (diff / (width/2))
    # action is one of "Bang-Left", "Bang-Right", "Straight", "None"
    diff: Optional[int]
    bias: Optional[float]
    action: str
    intersection: Optional[tuple]
    annotated: np.ndarray
    edges: np.ndarray


class LaneVision:
    def __init__(self, camera_index: int = 0, width: Optional[int] = None,
                 height: Optional[int] = None):
        self.cap = cv2.VideoCapture(camera_index)
        if width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera index {camera_index}")

    def read(self) -> Optional[LaneResult]:
        ret, frame = self.cap.read()
        if not ret:
            return None
        return self.process(frame)

    @staticmethod
    def process(frame: np.ndarray) -> LaneResult:
        height, width = frame.shape[:2]
        ideal_center = width // 2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        mask = np.zeros_like(gray)
        polygon = np.array([[
            (0, height),
            (width, height),
            (width, int(height * 0.4)),
            (0, int(height * 0.4)),
        ]])
        cv2.fillPoly(mask, polygon, 255)
        masked_gray = cv2.bitwise_and(gray, mask)

        _, binary = cv2.threshold(masked_gray, 200, 255, cv2.THRESH_BINARY)
        blurred = cv2.GaussianBlur(binary, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        edges_color = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

        annotated = frame.copy()
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 50,
                                minLineLength=50, maxLineGap=20)

        left_m, left_b, right_m, right_b = [], [], [], []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if x1 == x2:
                    continue
                m = (y2 - y1) / (x2 - x1)
                b = y1 - m * x1
                mid_x = (x1 + x2) / 2
                if m < -0.3 and mid_x < ideal_center:
                    left_m.append(m)
                    left_b.append(b)
                    cv2.line(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                elif m > 0.3 and mid_x > ideal_center:
                    right_m.append(m)
                    right_b.append(b)
                    cv2.line(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

        diff = None
        bias = None
        action = "None"
        intersection = None

        if left_m and right_m:
            avg_lm = float(np.mean(left_m))
            avg_lb = float(np.mean(left_b))
            avg_rm = float(np.mean(right_m))
            avg_rb = float(np.mean(right_b))

            x_int = int((avg_lb - avg_rb) / (avg_rm - avg_lm))
            y_int = int(avg_lm * x_int + avg_lb)
            diff = x_int - ideal_center
            bias = max(-1.0, min(1.0, diff / (width / 2.0)))
            intersection = (x_int, y_int)

            if diff > 0:
                action = "Bang-Right"
            elif diff < 0:
                action = "Bang-Left"
            else:
                action = "Straight"

            info = [
                f"L: y = {avg_lm:.2f}x + {avg_lb:.2f}",
                f"R: y = {avg_rm:.2f}x + {avg_rb:.2f}",
                f"Inter: ({x_int}, {y_int})",
                f"Ideal: {ideal_center}",
                f"Diff: {diff}  Bias: {bias:+.2f}",
                f"Action: {action}",
            ]
            for i, text in enumerate(info):
                cv2.putText(edges_color, text, (10, 30 + i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1,
                            cv2.LINE_AA)

            cv2.circle(annotated, intersection, 8, (0, 0, 255), -1)

        cv2.line(annotated, (ideal_center, height),
                 (ideal_center, height - 50), (255, 0, 0), 2)

        return LaneResult(
            diff=diff,
            bias=bias,
            action=action,
            intersection=intersection,
            annotated=annotated,
            edges=edges_color,
        )

    def close(self):
        self.cap.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default 0)")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--print-every", type=float, default=0.25,
                        help="Seconds between stdout prints (default 0.25)")
    args = parser.parse_args()

    vision = LaneVision(args.camera, args.width, args.height)
    last_print = 0.0

    print("Controls:  q = quit\n")
    try:
        while True:
            result = vision.read()
            if result is None:
                print("Camera read failed.")
                break

            cv2.imshow("Result", result.annotated)
            cv2.imshow("Masked Edges", result.edges)

            now = time.monotonic()
            if now - last_print >= args.print_every:
                if result.diff is None:
                    print("no lane")
                else:
                    print(f"diff = {result.diff:+4d}  "
                          f"bias = {result.bias:+.2f}  "
                          f"action = {result.action}")
                last_print = now

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        vision.close()
        cv2.destroyAllWindows()
        print("Closed.")


if __name__ == "__main__":
    main()
