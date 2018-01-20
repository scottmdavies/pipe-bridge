# pipe-bridge

## Python Reference



## OpenCV Reference

### Template Matching

+ Slides template image over input image

`cv2.matchTemplate() `

https://opencv-python-tutroals.readthedocs.io/en/latest/py_tutorials/py_imgproc/py_template_matching/py_template_matching.html#template-matching

+ Multi-scale
  + Reducing scale of input image increases matchTemplate speed
+ Template match between edge map representations
+ Template matching is translation invariant
+ Keypoint matching recommended to match rotated objects of unknown orientation
  + High computational expense of looping over rotations (5&deg; increments)
  + Rotation of template sybmols on technical drawings possible only likely to be transformed 0, 90, 270&deg;
+ __Recommended__ : Scale image to 600-800 pixels on largest dimension
+ __Recommended__ : CCOEFF

https://www.pyimagesearch.com/2015/01/26/multi-scale-template-matching-using-python-opencv/

### Keypoint Matching


### Features

+ Feature detection: Corners or blobs > edges > flat surface
+ Feature description: shape, colour, contrast

https://opencv-python-tutroals.readthedocs.io/en/latest/py_tutorials/py_feature2d/py_features_meaning/py_features_meaning.html#features-meaning

### Thoughts

+ Technical drawings
+ Digitally produced
+ White background
  + Black or coloured symbols, lines, and text
+ Specific Symbols
+ Lines indicating connections between symbols
+ Symbols potentially rotated at fixed angles
+ Connecting lines will run at 0 and 90&deg; to Y axis  


## Flask
+ Send / Receive images via flask
https://gist.github.com/kylehounslow/767fb72fde2ebdd010a0bf4242371594
