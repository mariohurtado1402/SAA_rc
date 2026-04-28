"""
Lane-detection helper for centering the car in a lane.

Mirrors the shape of the servo / esc helpers: a class you can import and
reuse from cmd_mux (or any control loop), plus a `main()` that runs it
standalone and shows the camera feed in real time.

Run as a standalone tester (Windows / WSL / Linux):
    uv run python -m helpers.vision_serial
    uv run python -m helpers.vision_serial --camera 1
    uv run python -m helpers.vision_serial --servo-port COM5
"""

import argparse
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .servo_serial import ANGLE_CENTER, ANGLE_MAX, ANGLE_MIN, SerialServo


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
                 height: Optional[int] = None, max_res: bool = False):
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera index {camera_index}")
        if max_res:
            # Ask for an absurdly large frame; V4L2 / DirectShow / AVFoundation
            # clamp to the highest mode the device actually supports.
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 4096)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 4096)
        if width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

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


def bias_to_angle(bias: Optional[float], deadzone: float, gain: int) -> int:
    """Map a normalized lane bias to a servo angle, with a center deadzone.

    `bias` in [-1, 1]. Inside the deadzone the servo holds center; outside,
    the response is rescaled so it grows continuously from 0 at the edge of
    the deadzone up to `gain` degrees at |bias| = 1.
    """
    if bias is None:
        return ANGLE_CENTER
    if abs(bias) < deadzone:
        return ANGLE_CENTER
    sign = 1.0 if bias > 0 else -1.0
    span = max(1e-6, 1.0 - deadzone)
    eff = (abs(bias) - deadzone) / span
    angle = int(round(ANGLE_CENTER + sign * eff * gain))
    return max(ANGLE_MIN, min(ANGLE_MAX, angle))


def _draw_lka_overlay(frame: np.ndarray, deadzone: float, gain: int,
                      target_angle: int, sent: bool) -> None:
    h, w = frame.shape[:2]
    cx = w // 2
    dz_px = int(deadzone * (w / 2.0))
    # Yellow deadzone band.
    overlay = frame.copy()
    cv2.rectangle(overlay, (cx - dz_px, 0), (cx + dz_px, h), (0, 255, 255), -1)
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
    cv2.line(frame, (cx - dz_px, 0), (cx - dz_px, h), (0, 200, 200), 1)
    cv2.line(frame, (cx + dz_px, 0), (cx + dz_px, h), (0, 200, 200), 1)
    label = f"servo={target_angle:3d}  dz={deadzone:.2f}  gain={gain:2d}"
    if not sent:
        label += "  (no port)"
    cv2.putText(frame, label, (10, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default 0)")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--max-res", action="store_true",
                        help="Probe and use the camera's largest supported "
                             "resolution. Ignored if --width/--height given.")
    parser.add_argument("--print-every", type=float, default=0.25,
                        help="Seconds between stdout prints (default 0.25)")
    parser.add_argument("--servo-port", default=None,
                        help="Serial port of the steering Nano (e.g. COM5, "
                             "/dev/ttyUSB0). Omit to run vision-only.")
    parser.add_argument("--servo-baud", type=int, default=115200)
    parser.add_argument("--deadzone", type=float, default=0.15,
                        help="Initial bias deadzone in [0, 1]. Tunable live "
                             "via the 'Deadzone x100' trackbar.")
    parser.add_argument("--gain", type=int, default=30,
                        help="Initial max servo deviation from center, in "
                             "degrees. Tunable live via the 'Gain' trackbar.")
    args = parser.parse_args()

    vision = LaneVision(args.camera, args.width, args.height,
                        max_res=args.max_res)
    print(f"Camera open at {vision.width}x{vision.height}.")

    servo: Optional[SerialServo] = None
    if args.servo_port:
        servo = SerialServo(args.servo_port, args.servo_baud)
        servo.center()
        print(f"Servo connected on {args.servo_port}, centered at "
              f"{ANGLE_CENTER} deg.")
    else:
        print("No --servo-port given; running vision-only (no servo output).")

    cv2.namedWindow("Result")
    cv2.createTrackbar("Deadzone x100", "Result",
                       int(max(0.0, min(1.0, args.deadzone)) * 100), 100,
                       lambda v: None)
    cv2.createTrackbar("Gain (deg)", "Result",
                       max(0, min(50, args.gain)), 50, lambda v: None)

    last_print = 0.0
    print("Controls:  q = quit\n")
    try:
        while True:
            result = vision.read()
            if result is None:
                print("Camera read failed.")
                break

            deadzone = cv2.getTrackbarPos("Deadzone x100", "Result") / 100.0
            gain = cv2.getTrackbarPos("Gain (deg)", "Result")

            target_angle = bias_to_angle(result.bias, deadzone, gain)
            if servo is not None:
                target_angle = servo.write_angle(target_angle)

            _draw_lka_overlay(result.annotated, deadzone, gain, target_angle,
                              servo is not None)

            cv2.imshow("Result", result.annotated)
            cv2.imshow("Masked Edges", result.edges)

            now = time.monotonic()
            if now - last_print >= args.print_every:
                if result.diff is None:
                    print(f"no lane | servo={target_angle}")
                else:
                    print(f"diff = {result.diff:+4d}  "
                          f"bias = {result.bias:+.2f}  "
                          f"action = {result.action:<10s}  "
                          f"servo = {target_angle:3d}  "
                          f"dz = {deadzone:.2f}  gain = {gain}")
                last_print = now

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        vision.close()
        if servo is not None:
            servo.center()
            servo.close()
        cv2.destroyAllWindows()
        print("Closed.")


if __name__ == "__main__":
    main()
