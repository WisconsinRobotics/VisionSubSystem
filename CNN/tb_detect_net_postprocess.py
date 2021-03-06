import math
import cv2
import numpy as np
import time
import os
from collections import deque

# "constants"
FRAME_RATE = 15
MAX_STACK_SIZE = 60
FT_TO_M_CONV_FACTOR = .3048        # [m/ft] obviously
M_TO_PX_CONV_FACTOR = 3779.5276    # [px/m] obviously
CAM_FOCAL_L = 112.0                # what unit is this?
TB_KNOWN_W = 2.6                   # [in]
IMG_W = 1920
IMG_H = 1080

frame_stack = []
output_info = []

# cv2 information
# "constants"
CIRCLE_MIN_R = 2
KERNEL_SIZE = 15

#min_HSV = np.array([30,50,0])
#max_HSV = np.array([50,255,255])
min_HSV = np.array([25,50,0])
max_HSV = np.array([75,255,255])

# return information
x_center_final = None
y_center_final = None
r_final = None
tb_dist_final = None
detect_timestamp = None

# NOTE: difficult/relevant test case images
#         - img_1042.jpg
#         - img_1036.jpg
#         - img_1014.jpg
#         - img_1010.jpg
#         - img_1003.jpg
#         - img_1000.jpg
#         - img_0974.jpg
#         - img_0973.jpg
#         - img_0956.jpg
#         - img_0955.jpg
#         - img_0954.jpg
#         - img_0950.jpg
#         - img_0942.jpg
#         - img_0924.jpg
#         - img_0914.jpg
#         - img_0912.jpg
#         - img_0879.jpg
#         - img_0875.jpg
temp_path = r"..\Training Data\tennis-ball-dataset\pics"
#temp_path = r".\tb_test_images"
debug = True
image_debug = True
advanced_debug = False

def sharpenImg(image):
    clahe = cv2.createCLAHE(clipLimit=5, tileGridSize=(5,5))

    lab_img = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l,a,b = cv2.split(lab_img)

    l2 = clahe.apply(l)

    lab_img = cv2.merge((l2,a,b))
    res_img = cv2.cvtColor(lab_img, cv2.COLOR_LAB2BGR)

    # DEBUG: display contrasted image
    #---------------------------------------------------------------------------
    if image_debug:
        print(" *** DEBUG: display contrasted image(s)")
        cv2.imshow('image', image)
        cv2.imshow('lab img', lab_img)
        cv2.imshow('res img', res_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    #---------------------------------------------------------------------------

    return res_img

def getHsvMask(image):
    hsv_img = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    temp_img = hsv_img.copy()

    # setup mask for image
    mask = cv2.inRange(hsv_img, min_HSV, max_HSV)
    #hsv_img[np.where(mask==0)] = 0

    # erode and dilate mask
    mask = cv2.erode(mask, None, iterations=1)
    mask = cv2.dilate(mask, None, iterations=1)
    hsv_img[np.where(mask==0)] = 0

    # DEBUG: display image
    #---------------------------------------------------------------------------
    if image_debug:
        print(" *** DEBUG: display hsv/masked images")
        cv2.imshow('image', image)
        cv2.imshow('hsv image', temp_img)
        cv2.imshow('masked image', hsv_img)
        cv2.imshow('mask', mask)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    #---------------------------------------------------------------------------

    return temp_img, hsv_img


def getBallLoc(image):
    # get circles using Hough Transform
    # NOTE: - param1 = higher threshold to Canny (apparently)
    #       - param2 = accumulator threshold, how large the pool is for similar circle centers
    circles = cv2.HoughCircles(image, cv2.HOUGH_GRADIENT, 1, 5, param1=255, param2=20, minRadius=5, maxRadius=0)
    if circles is None:
        print("No circles detected")

        return 0, 0, 0, 0
    circles = np.uint16(np.around(circles))

    # DEBUG: draw circles
    #---------------------------------------------------------------------------
    if advanced_debug:
        print(" *** DEBUG: draw circles")
        test_img = image.copy()
        for i in circles[0,:]:
            print("x: ", i[0], " y: ", i[1], " r: ", i[2])
            cv2.circle(test_img, (i[0], i[1]), i[2], (255, 255, 255), 2)
            cv2.circle(test_img, (i[0], i[1]), 2, (255, 255, 255), 3)
        print(len(circles[0,:]))
        cv2.imshow("detected circles with edge image", test_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        #exit()
    #---------------------------------------------------------------------------

    # get best circle
    x_best = circles[0,0,0]
    y_best = circles[0,0,1]
    r_best = circles[0,0,2]

    # -OR-

    # average all detected circles w/in a range
    x_tot = 0
    y_tot = 0
    r_tot = 0
    for x in circles[0,:]:
        x_tot += x[0]
        y_tot += x[1]
        r_tot += x[2]
    x_avg = int(round(x_tot/(len(circles[0,:]))))
    y_avg = int(round(y_tot/(len(circles[0,:]))))
    r_avg = int(round(r_tot/(len(circles[0,:]))))

    # DEBUG: draw averaged circles
    #---------------------------------------------------------------------------
    if image_debug:
        print(" *** DEBUG: draw \"best\" and averaged circle")
        test_img = image.copy()
        print("best x: ", x_best, " best y: ", y_best, " best r: ", r_best)
        cv2.circle(test_img, (x_best, y_best), r_best, (255, 255, 255), 1)
        cv2.circle(test_img, (x_best, y_best), 2, (255, 255, 255), 3)
        print("x_avg: ", x_avg, " y_avg: ", y_avg, " r_avg: ", r_avg)
        cv2.circle(test_img, (x_avg, y_avg), r_avg, (255, 255, 255), 2)
        cv2.circle(test_img, (x_avg, y_avg), 2, (255, 255, 255), 3)
        cv2.imshow("averaged circle with edge image", test_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    #---------------------------------------------------------------------------

    timestamp = time.time()

    #return x_avg, y_avg, r_avg, timestamp
    return x_best, y_best, r_best, timestamp


def getBallDist(x, y, r, h, w):
    # what was used in the Google adapted network
    # conversion between resolutions
    # for reference:
    #  - IMG_W or x_res = 1920
    #  - IMG_H or y_res = 1080
    #ymin, xmin, ymax, xmax = box
    #res = [IMG_W, IMG_H]
    #r = (ymax - ymin) * y_res

    # get distance
    dist_in = (TB_KNOWN_W * CAM_FOCAL_L) / (r*2)
    dist_ft = dist_in / 12
    dist = dist_ft / FT_TO_M_CONV_FACTOR

    # get angle from (0,0) in center of image
    #x_map = x - IMG_W/2
    #y_map = y - IMG_H/2
    x_map = x - w/2
    y_map = y - h/2
    euc_dist = math.hypot(x_map, y_map)
    euc_dist = euc_dist / M_TO_PX_CONV_FACTOR
    ang = math.asin(euc_dist / dist)

    # DEBUG
    #---------------------------------------------------------------------------
    if debug:
        print(" *** DEBUG: check distance and angle")
        print("x_map: ", x_map, ", y_map: ", y_map)
        print("euc_dist: ", euc_dist)
        print("Distance to Tennis Ball [m]: ", dist)
        print("Angle of Tennis Ball [rad]: ", ang)
    #---------------------------------------------------------------------------

    return dist, ang


def checkCircle(orig_hsv_image, hsv_image, x_start, y_start, r_avg, thresh, h, w):
    """
    Step types follow compass directions:
      - 0 = N
      - 1 = NE
      - 2 = E
      - 3 = SE
      - 4 = S
      - 5 = SW
      - 6 = W
      - 7 = NW
    """
    # DEBUG
    if advanced_debug:
        print(" *** DEBUG: create temp data structure")
        temp = []

    # format: [H, S, V]
    color_accept_low = [25,50,0]
    color_accept_high = [75,255,255]
    d = deque()
    circle_pts = 0
    color_range_pts = 0

    d.appendleft([x_start, y_start + 1, 0])
    d.appendleft([x_start + 1, y_start + 1, 1])
    d.appendleft([x_start + 1, y_start, 2])
    d.appendleft([x_start + 1, y_start - 1, 3])
    d.appendleft([x_start, y_start - 1, 4])
    d.appendleft([x_start - 1, y_start - 1, 5])
    d.appendleft([x_start - 1, y_start, 6])
    d.appendleft([x_start - 1, y_start + 1, 7])

    while (d):
        info = d.pop()
        if ((info[0] > 0) and (info[0] < (w - 1)) and (info[1] > 0) and (info[1] < (h - 1))):
            length = math.hypot(x_start - info[0], y_start - info[1])
            
            # DEBUG
            if advanced_debug:
                print(" *** DEBUG: check iterated pts")
                print("x: ", info[0], ", y: ", info[1], ", length: ", length)

            if length < r_avg:
                # DEBUG
                if advanced_debug:
                    print(" *** DEBUG: add pts to temp data structure")
                    temp.append([info[0], info[1]])

                # increment total pts in circle counter
                circle_pts += 1;

                # check if pxl values in range
                pxl = orig_hsv_image[info[1], info[0]]
                if ((pxl[0] > color_accept_low[0] and pxl[0] < color_accept_high[0]) and
                    (pxl[1] > color_accept_low[1] and pxl[1] < color_accept_high[1]) and 
                    (pxl[2] > color_accept_low[2] and pxl[2] < color_accept_high[2])):
                    # increment pts in color range counter
                    color_range_pts += 1;

                # continue to next pt(s)
                if (info[2] == 0):
                    d.appendleft([info[0], info[1] + 1, 0])
                elif (info[2] == 1):
                    d.appendleft([info[0], info[1] + 1, 0])
                    d.appendleft([info[0] + 1, info[1] + 1, 1])
                    d.appendleft([info[0] + 1, info[1], 2])
                elif (info[2] == 2):
                    d.appendleft([info[0] + 1, info[1], 2])
                elif (info[2] == 3):
                    d.appendleft([info[0] + 1, info[1], 2])
                    d.appendleft([info[0] + 1, info[1] - 1, 3])
                    d.appendleft([info[0], info[1] - 1, 4])
                elif (info[2] == 4):
                    d.appendleft([info[0], info[1] - 1, 4])
                elif (info[2] == 5):
                    d.appendleft([info[0], info[1] - 1, 4])
                    d.appendleft([info[0] - 1, info[1] - 1, 5])
                    d.appendleft([info[0] - 1, info[1], 6])
                elif (info[2] == 6):
                    d.appendleft([info[0] - 1, info[1], 6])
                else:
                    d.appendleft([info[0] - 1, info[1], 6])
                    d.appendleft([info[0] - 1, info[1] + 1, 7])
                    d.appendleft([info[0], info[1] + 1, 0])

    #DEBUG: show checked coordinates and other information
    #---------------------------------------------------------------------------
    if debug:
        print(" *** DEBUG: check iterated pts")
        if advanced_debug:
            test_img = hsv_image.copy()
            for i in temp:
                cv2.circle(test_img, (i[0], i[1]), 1, (255, 255, 255), 1)
                cv2.imshow("averaged circle with edge image", test_img)
                cv2.waitKey(1)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        print("x start: ", x_start, ", y start: ", y_start)
        print("# pts in color range: ", color_range_pts, ", # pts in circle: ", circle_pts, ", fraction of points in acceptable range: ", (color_range_pts / circle_pts))
    #---------------------------------------------------------------------------

    # check if percentage of in-range color pts is above acceptable threshold
    if (color_range_pts / circle_pts) > thresh:
        return True

    return False


def main():
    # see AI-ROCKS/Drive/Models/Camera.cs for references and structure
    # setup
    # ---------------------------------------------------------------------------
    # NOTE: replace <placeholder> code with what will be used for the image input
    # <placeholder>
    image_buf = []
    for f in os.listdir(temp_path):
        filepath = os.path.join(temp_path, f)
        image_buf.append(filepath)
    num_found = 0
    num_not_found = 0
    first = True
    test_cnt = 0

    global frame_stack
    start_time = time.time()

    # main loop
    while (True):
        # read and/or load next frame
        # ---------------------------------------------------------------------------
        # NOTE: replace <placeholder> code with what will be used for the image input
        # <placeholder>
        if not image_buf:
            break
        next_img= cv2.imread(image_buf.pop())
        test_cnt += 1
        if test_cnt > 100:
            break

        if len(frame_stack) >= MAX_STACK_SIZE:
            print("stack size = ", len(frame_stack))
            print("purging stack")
            frame_stack = []
        else:
            frame_stack.append(next_img)

            # TODO: check this calculation
            t_diff = time.time() - start_time
            print("\ntime calc", t_diff, ", ref: ", (1/15))
            if (t_diff > (1/15)) or first:
                first = False
                start_time = time.time()

                print("reading next image")
                img = frame_stack.pop()

                # pre-processing
                # ---------------------------------------------------------------------------
                height, width = img.shape[:2]

                gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                blur_img = cv2.medianBlur(img, KERNEL_SIZE)
                #gray_blur_img = cv2.cvtColor(blur_img, cv2.COLOR_BGR2GRAY)

                # DEBUG
                #---------------------------------------------------------------------------
                if debug:
                    print(" *** DEBUG: initial check")
                    print(str(width) + "x" + str(height))
                    if image_debug:
                        cv2.imshow('image', img)
                        cv2.imshow('gray image', gray_img)
                        #cv2.imshow('gray blurred image', gray_blur_img)
                        cv2.waitKey(0)
                        cv2.destroyAllWindows()
                #---------------------------------------------------------------------------

                # processing
                # ---------------------------------------------------------------------------
                # TODO: make a decision on this
                # use one of 2 methods:
                #   1. SIFT
                #   2. combination of feature detection (circles, color, contrast, etc.)
                # Method 1:
                #  - <SIFT method details>


                # Method 2: 
                #  - color
                orig_hsv_img, hsv_img = getHsvMask(blur_img)

                # get edge image
                edge_img = cv2.Canny(hsv_img, 0, 255, apertureSize=3, L2gradient=False)

                # DEBUG: check edge image
                #---------------------------------------------------------------------------
                if image_debug:
                    print(" *** DEBUG: display edge img")
                    cv2.imshow('edge img', edge_img)
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
                    #exit()
                #---------------------------------------------------------------------------

                #  - circles
                x_c, y_c, r, tstamp = getBallLoc(edge_img)
                if (0 == x_c) and (0 == y_c) and (0 == r) and (0 == tstamp):
                    num_not_found += 1
                    continue

                # DEBUG
                #---------------------------------------------------------------------------
                if debug:
                    print(" *** DEBUG: check detected circle info")
                    if advanced_debug:
                        for h in range((y_c-r),(y_c+r)):
                            for w in range((x_c-r),(x_c+r)):
                                print(hsv_img[h][w])
                                #cv2.circle(hsv_img, (w, h), 1, (255, 255, 255), 1)
                                cv2.imshow("test", hsv_img)
                                cv2.waitKey(1)
                            cv2.waitKey(0)
                        cv2.waitKey(0)
                        cv2.destroyAllWindows()
                    print("x_c: ", x_c, ", y_c: ", y_c, ", r: ", r, ", tstamp: ", tstamp)
                    #exit()
                #---------------------------------------------------------------------------

                #  - determine whether to keep or not
                found = checkCircle(orig_hsv_img, hsv_img, x_c, y_c, r, .7, height, width)
                
                # DEBUG
                if debug:
                    print(" *** DEBUG: check if acceptable circle found")
                    print("found? ", found)
                    #exit()

                # results
                # ---------------------------------------------------------------------------
                if found:
                    num_found += 1

                    #  - distance to ball
                    dist, angle = getBallDist(x_c, y_c, r, height, width)

                    # output information
                    # ---------------------------------------------------------------------------
                    # output information structure:
                    #   [x center, y center, radius, distance to ball, angle of ball, timestamp]
                    output_info = [x_c, y_c, r, dist, angle, tstamp]
                    # NOTE: replace <placeholder> code with what will be used for the image input
                    # <placeholder>
                    print(output_info)
                    #return output_info
                else:
                    num_not_found += 1
            else:
                time.sleep(.05)

    print("num found: ", num_found, ", num not found: ", num_not_found)
    print("end of main loop")

    return 0


if __name__ == "__main__":
  main()
