import cv2
import numpy as np

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break
        
    height, width = frame.shape[:2]
    ideal_center = width // 2

    grayScaleImage = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    mask = np.zeros_like(grayScaleImage)
    polygon = np.array([[(0, height), (width, height), (width, int(height * 0.4)), (0, int(height * 0.4))]])
    cv2.fillPoly(mask, polygon, 255)
    masked_gray = cv2.bitwise_and(grayScaleImage, mask)

    _, binaryImage = cv2.threshold(masked_gray, 200, 255, cv2.THRESH_BINARY)
    blurImage = cv2.GaussianBlur(binaryImage, (5, 5), 0)
    edgesImage = cv2.Canny(blurImage, 50, 150)
    
    edges_color = cv2.cvtColor(edgesImage, cv2.COLOR_GRAY2BGR)
    
    houghLinesPImage = frame.copy()
    linesP = cv2.HoughLinesP(edgesImage, 1, np.pi/180, 50, minLineLength=50, maxLineGap=20)
    
    left_m, left_b, right_m, right_b = [], [], [], []

    if linesP is not None:
        for line in linesP:
            x1, y1, x2, y2 = line[0]
            if x1 == x2: continue
            m = (y2 - y1) / (x2 - x1)
            b = y1 - m * x1
            mid_x = (x1 + x2) / 2
            
            if m < -0.3 and mid_x < ideal_center:
                left_m.append(m)
                left_b.append(b)
                cv2.line(houghLinesPImage, (x1, y1), (x2, y2), (0, 255, 0), 2)
            elif m > 0.3 and mid_x > ideal_center:
                right_m.append(m)
                right_b.append(b)
                cv2.line(houghLinesPImage, (x1, y1), (x2, y2), (0, 255, 0), 2)

    if left_m and right_m:
        avg_left_m = np.mean(left_m)
        avg_left_b = np.mean(left_b)
        avg_right_m = np.mean(right_m)
        avg_right_b = np.mean(right_b)
        
        x_int = int((avg_left_b - avg_right_b) / (avg_right_m - avg_left_m))
        y_int = int(avg_left_m * x_int + avg_left_b)
        diff = x_int - ideal_center
        
        if diff > 0: action = "Bang-Right"
        elif diff < 0: action = "Bang-Left"
        else: action = "Straight"
            
        info = [
            f"L: y = {avg_left_m:.2f}x + {avg_left_b:.2f}",
            f"R: y = {avg_right_m:.2f}x + {avg_right_b:.2f}",
            f"Inter: ({x_int}, {y_int})",
            f"Ideal: {ideal_center}",
            f"Diff: {diff}",
            f"Action: {action}"
        ]

        for i, text in enumerate(info):
            cv2.putText(edges_color, text, (10, 30 + (i * 25)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

        cv2.circle(houghLinesPImage, (x_int, y_int), 8, (0, 0, 255), -1)
        cv2.line(houghLinesPImage, (ideal_center, height), (ideal_center, height - 50), (255, 0, 0), 2)

    cv2.imshow('Result', houghLinesPImage)
    cv2.imshow('Masked Edges', edges_color)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()