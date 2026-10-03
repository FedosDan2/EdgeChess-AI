import cv2


class BoardTransformer:
    def crop(self, image, bbox):
        x1, y1, x2, y2 = map(int, bbox)

        return image[y1:y2, x1:x2]