#!/usr/bin/env python3
"""Ask a running ComfyUI which nodes it has and fail if mvpipe's are missing. Standard library only.

  check_nodes.py [--url http://127.0.0.1:8188] [--wait 120]
"""
import argparse, json, sys, time, urllib.request

REQUIRED = {
    "EmptyMiniMaxH3LatentAV": "Empty MiniMax H3 AV Latent",
    "MiniMaxH3ReferenceToVideo": "MiniMax H3 Reference to Video",
    "MiniMaxH3AddGuide": "Add Guide for MiniMax H3 (continuation and end image)",
    "MiniMaxH3SigmaShift": "ModelSamplingMiniMaxH3",
    "MiniMaxH3FunControlNetApply": "Apply MiniMax H3 Fun ControlNet",
    "MinimaxH3LatentUpscaler3D": "Minimax H3 Latent Upscaler (3D), custom node",
    "VHS_VideoCombine": "VideoHelperSuite, custom node",
    "ImageBatchExtendWithOverlap": "KJNodes, custom node (spot check)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--wait", type=int, default=0, help="seconds to keep retrying while ComfyUI starts")
    a = ap.parse_args()
    deadline, info = time.time() + a.wait, None
    while info is None:
        try:
            info = json.load(urllib.request.urlopen(a.url + "/object_info", timeout=30))
        except Exception as err:
            if time.time() > deadline:
                print("ComfyUI not reachable at %s: %s" % (a.url, err))
                return 2
            time.sleep(3)
    bad = 0
    for node, label in REQUIRED.items():
        ok = node in info
        bad += not ok
        print("%-8s %s  [%s]" % ("OK" if ok else "MISSING", node, label))
    print("%d nodes total, %d required missing" % (len(info), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
