import argparse
import cv2
import os

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input", required=True, help="drawing file containing symbols", type=str)
parser.add_argument("-o", "--output", required=True, help="location for saving cropped symbols", type=str)
args = parser.parse_args()


if os.path.exists(args.input)== False:
    print("[WARNING] Symbol drawing location: not found")
    exit()
print("[INFO] Symbol drawing location: {}".format(args.input))

if os.path.exists(args.output)== False:
    print("[WARNING] Cropped symbol location: not found")
    exit()
print("[INFO] Cropped symbol location: {}".format(args.output))

symbol_name = None
while True:
    symbol_drawing = cv2.imread(args.input)
    fromCenter = False
    roi = cv2.selectROI(symbol_drawing, fromCenter)
    cv2.destroyAllWindows()
    symbol_crop = symbol_drawing[int(roi[1]):int(roi[1] + roi[3]), int(roi[0]):int(roi[0] + roi[2])]
    symbol_name = input("Symbol name (exit to end): ")

    if symbol_name != 'exit':
        base_path = args.output
        symbol_file = os.path.join(base_path, (symbol_name +".png"))
        cv2.imwrite(symbol_file, symbol_crop)
        print(symbol_crop.shape[0:2])
        print("[INFO] Saving '{}'".format(symbol_file))

    elif symbol_name == 'exit':
        print("[INFO] Exiting '{}'".format(__file__))
        break
