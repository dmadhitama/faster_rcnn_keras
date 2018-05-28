import sys
import numpy as np
import keras.backend as K
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

def parse_label(xml_file):
    try:
        tree = ET.parse(xml_file)
    except Exception:
        print('Failed to parse: ' + xml_file, file=sys.stderr)
        return None
    root = tree.getroot()
    w_scale=1
    h_scale=1
    for x in root.iter('width'):
        if int(x.text) < 333:
            w_scale=333/float(x.text)
    for x in root.iter('height'):
        if int(x.text) < 333:
            h_scale=333/float(x.text)
    category=[]
    xmin=[]
    ymin=[]
    xmax=[]
    ymax=[]
    for x in root.iter('name'):
        category.append(x.text)
    for x in root.iter('xmin'):
        xmin.append(int(x.text)*w_scale)
    for x in root.iter('ymin'):
        ymin.append(int(x.text)*h_scale)
    for x in root.iter('xmax'):
        xmax.append(int(x.text)*w_scale)
    for x in root.iter('ymax'):
        ymax.append(int(x.text)*h_scale)
    gt_boxes=[list(box) for box in zip(xmin,ymin,xmax,ymax)]
    return category, np.asarray(gt_boxes, np.float), (h_scale,w_scale)


def loss_cls(y_true, y_pred):
    print(y_true,y_pred)
    output_scores = K.reshape(y_pred, (1, -1))
    y_true = K.reshape(y_true, (1, -1))

    condition = K.not_equal(y_true, -1)
    indices = K.tf.where(condition)
    indices = K.expand_dims(indices, 0)

    target = K.tf.gather_nd(y_true, indices)
    output = K.tf.gather_nd(output_scores, indices)
    loss = K.binary_crossentropy(target, output)
    return loss


def smoothL1(y_true, y_pred):
    nd=K.tf.where(K.tf.not_equal(y_true,0))
    y_true=K.tf.gather_nd(y_true,nd)
    y_pred=K.tf.gather_nd(y_pred,nd)
    x   = K.tf.losses.huber_loss(y_true,y_pred)
#     x   = K.switch(x < HUBER_DELTA, 0.5 * x ** 2, HUBER_DELTA * (x - 0.5 * HUBER_DELTA))
    return  K.sum(x)


def draw_anchors(img_path, anchors, pad_size=50):
    im = Image.open(img_path)
    w,h=im.size
    a4im = Image.new('RGB',
                    (w+2*pad_size, h+2*pad_size),   # A4 at 72dpi
                    (255, 255, 255))  # White
    a4im.paste(im, (pad_size,pad_size))  # Not centered, top-left corner
    for a in anchors:
        a=(a+pad_size).astype(int).tolist()
        draw = ImageDraw.Draw(a4im)
        draw.rectangle(a,outline=(255,0,0), fill=None)
    return a4im

def generate_anchors(base_width=16, base_height=16, ratios=[0.5, 1, 2],
                     scales=np.asarray([3,6,12])):
    """
    Generate anchor (reference) windows by enumerating aspect ratios X
    scales wrt a reference (0, 0, w_stride-1, h_stride-1) window.
    """

    base_anchor = np.array([1, 1, base_width, base_height]) - 1
    ratio_anchors = _ratio_enum(base_anchor, ratios)
    anchors = np.vstack([_scale_enum(ratio_anchors[i, :], scales)
                         for i in range(ratio_anchors.shape[0])])
    return anchors

def _whctrs(anchor):
    """
    Return width, height, x center, and y center for an anchor (window).
    """

    w = anchor[2] - anchor[0] + 1
    h = anchor[3] - anchor[1] + 1
    x_ctr = anchor[0] + 0.5 * (w - 1)
    y_ctr = anchor[1] + 0.5 * (h - 1)
    return w, h, x_ctr, y_ctr

def _mkanchors(ws, hs, x_ctr, y_ctr):
    """
    Given a vector of widths (ws) and heights (hs) around a center
    (x_ctr, y_ctr), output a set of anchors (windows).
    """

    ws = ws[:, np.newaxis]
    hs = hs[:, np.newaxis]
    anchors = np.hstack((x_ctr - 0.5 * (ws - 1),
                         y_ctr - 0.5 * (hs - 1),
                         x_ctr + 0.5 * (ws - 1),
                         y_ctr + 0.5 * (hs - 1)))
    return anchors

def _ratio_enum(anchor, ratios):
    """
    Enumerate a set of anchors for each aspect ratio wrt an anchor.
    """

    w, h, x_ctr, y_ctr = _whctrs(anchor)
    size = w * h
    size_ratios = size / ratios
    ws = np.round(np.sqrt(size_ratios))
    hs = np.round(ws * ratios)
    anchors = _mkanchors(ws, hs, x_ctr, y_ctr)
    return anchors

def _scale_enum(anchor, scales):
    """
    Enumerate a set of anchors for each scale wrt an anchor.
    """

    w, h, x_ctr, y_ctr = _whctrs(anchor)
    ws = w * scales
    hs = h * scales
    anchors = _mkanchors(ws, hs, x_ctr, y_ctr)
    return anchors

if __name__ == '__main__':
    import time
    t = time.time()
    a = generate_anchors(37,37)
    print(a)



def bbox_transform(ex_rois, gt_rois):
    ex_widths = ex_rois[:, 2] - ex_rois[:, 0] + 1.0
    ex_heights = ex_rois[:, 3] - ex_rois[:, 1] + 1.0
    ex_ctr_x = ex_rois[:, 0] + 0.5 * ex_widths
    ex_ctr_y = ex_rois[:, 1] + 0.5 * ex_heights

    gt_widths = gt_rois[:, 2] - gt_rois[:, 0] + 1.0
    gt_heights = gt_rois[:, 3] - gt_rois[:, 1] + 1.0
    gt_ctr_x = gt_rois[:, 0] + 0.5 * gt_widths
    gt_ctr_y = gt_rois[:, 1] + 0.5 * gt_heights

    targets_dx = (gt_ctr_x - ex_ctr_x) / ex_widths
    targets_dy = (gt_ctr_y - ex_ctr_y) / ex_heights
    targets_dw = np.log(gt_widths / ex_widths)
    targets_dh = np.log(gt_heights / ex_heights)

    targets = np.stack((targets_dx, targets_dy, targets_dw, targets_dh))

    targets = np.transpose(targets)

    return targets

def bbox_overlaps(boxes, query_boxes):
    """
    Parameters
    ----------
    boxes: (N, 4) ndarray of float
    query_boxes: (K, 4) ndarray of float
    Returns
    -------
    overlaps: (N, K) ndarray of overlap between boxes and query_boxes
    """
    boxes=boxes.astype(int)
    N = boxes.shape[0]
    K = query_boxes.shape[0]

    overlaps = np.zeros((N, K), dtype=np.float)

    for k in range(K):
        box_area = ((query_boxes[k, 2] - query_boxes[k, 0] + 1) * (query_boxes[k, 3] - query_boxes[k, 1] + 1))
        for n in range(N):
            iw = (min(boxes[n, 2], query_boxes[k, 2]) - max(boxes[n, 0], query_boxes[k, 0]) + 1)
            if iw > 0:
                ih = (min(boxes[n, 3], query_boxes[k, 3]) - max(boxes[n, 1], query_boxes[k, 1]) + 1)

                if ih > 0:
                    ua = float((boxes[n, 2] - boxes[n, 0] + 1) * (boxes[n, 3] - boxes[n, 1] + 1) + box_area - iw * ih)
                    overlaps[n, k] = iw * ih / ua

    return overlaps

def unmap(data, count, inds, fill=0):
    """ Unmap a subset of item (data) back to the original set of items (of
    size count) """
    if len(data.shape) == 1:
        ret = np.empty((count, ), dtype=np.float32)
        ret.fill(fill)
        ret[inds] = data
    else:
        ret = np.empty((count, ) + data.shape[1:], dtype=np.float32)
        ret.fill(fill)
        ret[inds, :] = data
    return ret