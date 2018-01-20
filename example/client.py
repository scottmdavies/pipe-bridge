import requests
import json
import cv2
from pathlib import Path


addr = 'http://localhost:5000'
test_url = addr + '/api/test'
pathname = '/home/'

# check 
if Path(pathname).exists() == True:
    image_suffix = PurePosixPath(input).suffix
    else:
    print("File does not exist")
    break

# prepare headers for http request
content_type = 'image/' + image_suffix 
headers = {'content-type': content_type}

img = cv2.imread(input)
# encode image as jpeg
_, img_encoded = cv2.imencode(image_suffix, img)
# send http request with image and receive response
response = requests.post(test_url, data=img_encoded.tostring(), headers=headers)
# decode response
print json.loads(response.text)

# expected output: {u'message': u'image received. size=124x124'}
