import json
import csv
from pathlib import Path
from PIL import Image

predict_dir = Path("outputs/ec2_predict/GH/v2026-09-20/general_kleesoft_purple_allround_purple/yolo26m_img960_e100")
summary_csv = predict_dir / "summary.csv"
ls_export_json = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/label_studio/exports/label_studio_export.json")
images_dir = Path("datasets/GH/v2026-09-20/general_kleesoft_purple_allround_purple/predict/images/yolo26m_img960_e100")

# 1. Load Ground Truth from Label Studio Export
ls_data = json.loads(ls_export_json.read_text(encoding="utf-8"))
gt_by_hash = {}
for task in ls_data:
    img_url = task.get("data", {}).get("image", "")
    fn = Path(img_url.split("?d=")[-1] if "?d=" in img_url else img_url).name
    h = fn.split('.')[0].split('_')[-1]
    
    boxes = []
    for anno in task.get("annotations", []):
        for res in anno.get("result", []):
            if res.get("type") == "rectanglelabels":
                val = res.get("value", {})
                labels = val.get("rectanglelabels", [])
                for l in labels:
                    boxes.append({
                        "label": l,
                        # percentage 0-100
                        "x": val.get("x", 0),
                        "y": val.get("y", 0),
                        "w": val.get("width", 0),
                        "h": val.get("height", 0)
                    })
    gt_by_hash[h] = {
        "filename": fn,
        "boxes": boxes,
        "task_id": task.get("id")
    }

# 2. Load Predictions
preds_by_hash = {}
with open(summary_csv, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        img_name = Path(row['local_image']).name
        h = img_name.split('.')[0].split('_')[-1]
        
        jf = predict_dir / "json" / Path(row['json_file']).name
        boxes = []
        if jf.exists():
            jd = json.loads(jf.read_text(encoding='utf-8'))
            for det in jd.get("detections", []):
                boxes.append(det)
        
        preds_by_hash[h] = {
            "row": row,
            "img_name": img_name,
            "boxes": boxes,
            "total_count": int(row['total_count'])
        }

print(f"Total predict images: {len(preds_by_hash)}")

def compute_iou(boxA, boxB):
    # boxA, boxB: [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxBArea = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])
    unionArea = boxAArea + boxBArea - interArea
    if unionArea <= 0:
        return 0.0
    return interArea / unionArea

# Evaluate across all 379 images
# Let's track:
# - Object-level (IoU >= 0.5)
# - Image-level
total_gt_objects = 0
total_pred_objects = 0

tp_objects = 0
fp_objects = 0
fn_objects = 0

by_class_metrics = {
    "allround_purple": {"gt": 0, "pred": 0, "tp": 0, "fp": 0, "fn": 0},
    "kleesoft_purple": {"gt": 0, "pred": 0, "tp": 0, "fp": 0, "fn": 0}
}

# Image-level tracking
img_gt_positive = 0
img_gt_negative = 0

img_tp = 0 # GT > 0 and Pred > 0
img_fn = 0 # GT > 0 and Pred == 0
img_fp = 0 # GT == 0 and Pred > 0
img_tn = 0 # GT == 0 and Pred == 0

per_image_details = []

for h, pred_info in preds_by_hash.items():
    gt_info = gt_by_hash.get(h, {"boxes": []})
    gt_boxes_raw = gt_info["boxes"]
    
    # Get image dimensions to convert GT from percentage to pixels
    local_img_path = images_dir / pred_info["img_name"]
    img_w, img_h = 1000, 1000 # fallback
    if local_img_path.exists():
        try:
            with Image.open(local_img_path) as im:
                img_w, img_h = im.size
        except Exception:
            pass
            
    # Convert GT boxes to [x1, y1, x2, y2]
    gt_boxes = []
    for gb in gt_boxes_raw:
        x1 = (gb["x"] / 100.0) * img_w
        y1 = (gb["y"] / 100.0) * img_h
        x2 = ((gb["x"] + gb["w"]) / 100.0) * img_w
        y2 = ((gb["y"] + gb["h"]) / 100.0) * img_h
        gt_boxes.append({
            "label": gb["label"],
            "xyxy": [x1, y1, x2, y2],
            "matched": False
        })
        
    p_boxes = []
    for pb in pred_info["boxes"]:
        p_boxes.append({
            "label": pb["class_name"],
            "xyxy": pb["xyxy"],
            "conf": pb.get("confidence", 1.0),
            "matched": False
        })
        
    # Stats
    n_gt = len(gt_boxes)
    n_pred = len(p_boxes)
    total_gt_objects += n_gt
    total_pred_objects += n_pred
    
    # Image level
    if n_gt > 0:
        img_gt_positive += 1
        if n_pred > 0:
            img_tp += 1
        else:
            img_fn += 1
    else:
        img_gt_negative += 1
        if n_pred > 0:
            img_fp += 1
        else:
            img_tn += 1
            
    # Box matching: greedy match with IoU >= 0.5
    # sort predictions by confidence desc
    p_boxes.sort(key=lambda x: x["conf"], reverse=True)
    img_tp_box = 0
    img_fp_box = 0
    
    for pb in p_boxes:
        best_iou = 0.0
        best_gt_idx = -1
        for g_idx, gb in enumerate(gt_boxes):
            if gb["matched"]:
                continue
            if gb["label"] != pb["label"]:
                continue
            iou = compute_iou(pb["xyxy"], gb["xyxy"])
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = g_idx
                
        if best_iou >= 0.5 and best_gt_idx >= 0:
            gt_boxes[best_gt_idx]["matched"] = True
            pb["matched"] = True
            tp_objects += 1
            img_tp_box += 1
            if pb["label"] in by_class_metrics:
                by_class_metrics[pb["label"]]["tp"] += 1
        else:
            fp_objects += 1
            img_fp_box += 1
            if pb["label"] in by_class_metrics:
                by_class_metrics[pb["label"]]["fp"] += 1
                
    img_fn_box = sum(1 for gb in gt_boxes if not gb["matched"])
    fn_objects += img_fn_box
    
    for gb in gt_boxes:
        if gb["label"] in by_class_metrics:
            by_class_metrics[gb["label"]]["gt"] += 1
            if not gb["matched"]:
                by_class_metrics[gb["label"]]["fn"] += 1
                
    for pb in p_boxes:
        if pb["label"] in by_class_metrics:
            by_class_metrics[pb["label"]]["pred"] += 1

    per_image_details.append({
        "hash": h,
        "image_name": pred_info["img_name"],
        "gt_count": n_gt,
        "pred_count": n_pred,
        "tp": img_tp_box,
        "fp": img_fp_box,
        "fn": img_fn_box
    })

print("\n" + "="*50)
print("【目标级别 (Object / 包装框级别) 统计指标】")
print("="*50)
print(f"总图片数: {len(preds_by_hash)}")
print(f"应识别目标总数 (Ground Truth): {total_gt_objects}")
print(f"实际识别目标总数 (Predictions): {total_pred_objects}")
print(f"① 应识别且已识别 (True Positives, TP): {tp_objects}")
print(f"② 应识别但未识别 (漏检, False Negatives, FN): {fn_objects}")
print(f"③ 不应识别却识别 (误检, False Positives, FP): {fp_objects}")

prec = tp_objects / total_pred_objects if total_pred_objects > 0 else 0
rec = tp_objects / total_gt_objects if total_gt_objects > 0 else 0
f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
print(f"准确率 (Precision): {prec*100:.2f}% ({tp_objects}/{total_pred_objects})")
print(f"召回率 (Recall):    {rec*100:.2f}% ({tp_objects}/{total_gt_objects})")
print(f"F1 得分 (F1 Score): {f1:.4f}")

print("\n【分品牌统计明细】")
for cls_name, m in by_class_metrics.items():
    c_p = m["tp"] / m["pred"] if m["pred"] > 0 else 0
    c_r = m["tp"] / m["gt"] if m["gt"] > 0 else 0
    print(f"  • {cls_name}: 应识别(GT)={m['gt']}, 预测={m['pred']}, TP={m['tp']}, FN(漏检)={m['fn']}, FP(误检)={m['fp']} | Precision={c_p*100:.2f}%, Recall={c_r*100:.2f}%")

print("\n" + "="*50)
print("【图片级别 (Image / 检查是否合格维度) 统计指标】")
print("="*50)
print(f"正样本图片 (有目标商品): {img_gt_positive} 张")
print(f"负样本图片 (无目标商品): {img_gt_negative} 张")
print(f"① 正样本且已识别 (图片级 TP): {img_tp} 张 (召回检出率: {img_tp/img_gt_positive*100:.2f}%)")
print(f"② 正样本漏识别为0 (图片级 FN): {img_fn} 张 (漏检率: {img_fn/img_gt_positive*100:.2f}%)")
print(f"③ 负样本误报有目标 (图片级 FP): {img_fp} 张 (误报率: {img_fp/img_gt_negative*100:.2f}%)")
print(f"④ 负样本正确判定为0 (图片级 TN): {img_tn} 张 (负样本准确率: {img_tn/img_gt_negative*100:.2f}%)")
img_acc = (img_tp + img_tn) / len(preds_by_hash)
print(f"图片级整体验收准确率 (TP+TN)/Total: {img_acc*100:.2f}% ({img_tp+img_tn}/{len(preds_by_hash)})")

