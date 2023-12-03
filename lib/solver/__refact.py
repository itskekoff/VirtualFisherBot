import numpy as np


def get_colors(image_array, limit=7):
    width, height, channels = image_array.shape
    image_array_flat = image_array.reshape((width * height, channels))
    tuple_array = zip(image_array_flat[:, 0], image_array_flat[:, 1], image_array_flat[:, 2])

    colors = {}
    for i, color in enumerate(tuple_array):
        if color not in colors:
            if len(colors) >= limit:
                continue
        x, y = int(i % height), int(i / height)
        if color not in colors.keys():
            colors[color] = {"left": x, "top": y, "right": x, "bottom": y}
        if x < colors[color]["left"]:
            colors[color]["left"] = x
        if y < colors[color]["top"]:
            colors[color]["top"] = y
        if y > colors[color]["bottom"]:
            colors[color]["bottom"] = y
        if x > colors[color]["right"]:
            colors[color]["right"] = x

    colors = dict(sorted(colors.items(), key=lambda e: e[1]["left"]))  # sort by left

    return colors


def crop_colors(colors, image):
    for channel in colors.values():
        channel["bottom"] += 1
        channel["right"] += 1
        char_image = image[channel["top"]:channel["bottom"], channel["left"]:channel["right"]]
        yield char_image


def filter_colors(images, colors_map):
    colors = list(colors_map.keys())
    bg = colors[0]
    next(images)
    for img, fg in zip(images, colors[1:]):
        a = np.copy(img)
        mask_fg = (img[:, :, 0] == fg[0]) & (img[:, :, 1] == fg[1]) & (img[:, :, 2] == fg[2])
        mask_bg = (img[:, :, 0] == bg[0]) & (img[:, :, 1] == bg[1]) & (img[:, :, 2] == bg[2])
        a[:, :, :] = 0.5
        a[mask_fg] = 0.0
        a[mask_bg] = 1.0
        yield a


def resize_images(images):
    for img in images:
        if img.shape[0] < 16:
            pad_width = ((0, 16 - img.shape[0]), (0, 0), (0, 0))
            img = np.pad(img, pad_width, mode='constant', constant_values=1)
        if img.shape[1] < 16:
            pad_width = ((0, 0), (0, 16 - img.shape[1]), (0, 0))
            img = np.pad(img, pad_width, mode='constant', constant_values=1)

        width, height, channels = img.shape
        pixels = []  # [(0, 0, 0), ..., (0, 1, 0)]
        for x, row in enumerate(img):
            for y, pix in enumerate(row):
                pixels.append((pix[0], int(16 * x / width), int(16 * y / height)))
        a = np.array([[(1, 1, 1)] * 16] * 16, dtype=img.dtype)
        for pix in pixels:
            if pix[0] < a[pix[1]][pix[2]][0]:
                a[pix[1]][pix[2]] = (pix[0], pix[0], pix[0])
        yield a


def refact_image(image_array, limit=7):
    colors = get_colors(image_array, limit=limit)
    pieces = crop_colors(colors, image_array)
    filtered_pics = filter_colors(pieces, colors)
    resized_pics = resize_images(filtered_pics)
    return resized_pics
