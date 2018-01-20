#

import os
import time
import argparse
import cv2
import numpy as np
from imutils import paths

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--symbols", required=True, help="folder containing symbols", type=str)
parser.add_argument("-d", "--drawings", required=False, help="drawings", type=str)
args = parser.parse_args()

if os.path.exists(args.symbols)== False:
    print("[WARNING] Symbol drawing location: not found")
    exit()
print("[INFO] Symbol drawing location: {}".format(args.symbols))

if os.path.exists(args.drawings)== False:
    print("[WARNING] Cropped symbol location: not found")
    exit()
print("[INFO] Drawing location: {}".format(args.drawings))

start = time.time()
symbol_count = []
symbol_list = {}

drawingpaths = list(paths.list_images(args.drawings))
symbolpaths = list(paths.list_images(args.symbols))

for d in drawingpaths:
    print(d)
    drawing = cv2.imread(d)
    drawing_gray = cv2.cvtColor(drawing, cv2.COLOR_RGB2GRAY)
    drawing_canny = cv2.Canny(drawing_gray, 50, 200)
    height, width, channels = drawing.shape
    blank_image = np.zeros((height, width, 3), np.uint8)
    
    for s in symbolpaths:
        print(s)

        symbol = cv2.imread(s)
        template_gray = cv2.cvtColor(symbol, cv2.COLOR_RGB2GRAY)
        template_canny = cv2.Canny(template_gray, 50, 200)
        
        w, h = template_gray.shape[::-1]
        # sliding window across drawing_canny removing previously detected break into columns
        res = cv2.matchTemplate(drawing_canny,template_canny,cv2.TM_CCOEFF_NORMED)
        
        threshold = 0.9
        loc = np.where( res >= threshold)
        for pt in zip(*loc[::-1]):
            cv2.rectangle(blank_image, pt, (pt[0] + w, pt[1] + h), (0,255,255), -1)

        count = np.count_nonzero(loc[:1])
        symbol_count.append(count)
        sym = np.count_nonzero(loc[:1])
        l = symbol_list.get(s,[])
        l.append(sym)
        symbol_list[s] = l



        blend = cv2.addWeighted(drawing, 0.7, blank_image, 0.3, 0)


print("[INFO] processed {} symbols in {:.2f} seconds".format(sum(symbol_count), time.time() - start))
print("[INFO] processed {} drawings in {:.2f} seconds".format(len(drawingpaths), time.time() - start))

cv2.namedWindow("Drawing", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Drawing", 500, 500)
cv2.imshow("Drawing", blend)
cv2.waitKey(0)
