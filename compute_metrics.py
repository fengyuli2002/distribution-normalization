'''
Computes metrics for Flickr8K.
'''
from pathlib import Path
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd
import argparse
import warnings
import torch
import numpy as np
import json
import os
import scipy.stats
import clipscore
import sys
import random
import other_metrics
from tqdm import tqdm, trange
from clip_retrieval import compute_retrieval
from clipscore import Pascal50sDataset


IMAGE_CAPTION_METRICS = Path('/share/cuvl/image_caption_metrics')
FLICKR8K_DIR = Path(IMAGE_CAPTION_METRICS, 'flickr8k')
FLICKR30K_DIR = Path(IMAGE_CAPTION_METRICS, 'flickr30k')
MSCOCO_DIR = Path(IMAGE_CAPTION_METRICS, 'MSCOCO_VAL2014')
COMPOSITE_DIR = Path(IMAGE_CAPTION_METRICS, 'composite')
PASCAL_DIR = Path(IMAGE_CAPTION_METRICS, 'pascal')


device = "cuda" if torch.cuda.is_available() else "cpu"
if device == 'cpu':
    warnings.warn('Running on CPU.')


def composite_data_cleaning(dataframe: pd.DataFrame) -> pd.DataFrame:
    '''
    Cleans the composite thoroughness dataset.
    '''
    columns = ['Input.image_url']
    for i in range(1, 5):
        columns.append(f'Input.text{i}')
        columns.append(f'Answer.Q{i}Answer')
    dataframe = dataframe.filter(columns)
    dataframe = dataframe.dropna()
    return dataframe

def compute_human_correlation(model_name, input_json, image_directory, dataset='flickr8k-expert', tauvariant='c', args=None):
    images = []
    candidates = []
    human_scores = []
    refs = []

    # used for debugging
    counter = 0

    # load flickr8k-expert dataset
    if dataset == 'flickr8k-expert':
        data = {}
        with open(input_json) as f:
            data.update(json.load(f))
        print('Loaded {} images'.format(len(data)))
        for k, v in list(data.items()):
            for human_judgement in v['human_judgement']:
                if np.isnan(human_judgement['rating']):
                    print('NaN')
                    continue
                images.append(image_directory + v['image_path'])
                candidates.append(' '.join(human_judgement['caption'].split()))
                human_scores.append(human_judgement['rating'])
                refs.append([' '.join(gt.split()) for gt in v['ground_truth']])

    # load thumb dataset
    elif dataset == 'thumb':
        with open(input_json, 'r') as json_file:
            data = list(json_file)
        with open(Path(MSCOCO_DIR, 'THumB/mscoco/mscoco_references.json'), 'r') as json_file:
            data_refs = list(json_file)
        segid2refs = {}
        for f in data_refs:
            d = json.loads(f)
            segid2refs[int(d['seg_id'])] = d['refs']
        print('Loaded {} images'.format(len(data)))
        for json_str in data:
            v = json.loads(json_str)
            images.append(image_directory + v['image'])
            refs.append(segid2refs[int(v['seg_id'])])
            candidates.append(v['hyp'])
            human_scores.append(v['human_score'])

    # load pascal dataset
    elif dataset == 'pascal':
        ds = Pascal50sDataset()
        images = [os.path.join(os.path.join(
            ds.root, "images"), d[0][0]) for d in ds.data]
        refs = ds.references

    # load composite dataset
    elif dataset == 'composite':
        image_caption_pairs_30k_correctness = pd.read_csv(
            f'{COMPOSITE_DIR}/30k_correctness.csv', sep=';')
        image_caption_pairs_30k_correctness = composite_data_cleaning(
            image_caption_pairs_30k_correctness)
        image_caption_pairs_30k_thoroughness = pd.read_csv(
            f'{COMPOSITE_DIR}/30k_throughness.csv', sep=';')
        image_caption_pairs_30k_thoroughness = composite_data_cleaning(
            image_caption_pairs_30k_thoroughness)
        for _, row in image_caption_pairs_30k_correctness.iterrows():
            image_dir = os.path.basename(row['Input.image_url'])
            ref = [row['Input.text1'], row['Input.text2'],
                   row['Input.text3'], row['Input.text4']]
            for i in range(4):
                images.append(f'{FLICKR30K_DIR}/flickr30k_images/{image_dir}')
                candidates.append(row[f'Input.text{i + 1}'])
                human_scores.append(row[f'Answer.Q{i + 1}Answer'])
                refs.append(ref)
        # for _, row in image_caption_pairs_30k_thoroughness.iterrows():
        #     image_dir_long = row['Input.image_url']
        #     image_dir = os.path.basename(image_dir_long)
        #     ref = [row['Input.text1'], row['Input.text2'], row['Input.text3'], row['Input.text4']]
        #     for i in range(4):
        #         images.append(f'{FLICKR30K_DIR}/flickr30k_images/{image_dir}')
        #         row_correctness = image_caption_pairs_30k_correctness.loc[
        #             image_caption_pairs_30k_correctness['Input.image_url'] == image_dir_long].to_numpy()
        #         if len(row_correctness) == 0:
        #             break
        #         candidates.append(row[f'Input.text{i + 1}'])
        #         human_scores.append(
        #             (float(row[f'Answer.Q{i + 1}Answer']) + float(row_correctness[0][i * 2 + 2])))
        #         refs.append(ref)

        image_caption_pairs_coco_correctness = pd.read_csv(
            f'{COMPOSITE_DIR}/coco_correctness.csv', sep=';')
        image_caption_pairs_coco_correctness = composite_data_cleaning(
            image_caption_pairs_coco_correctness)
        image_caption_pairs_coco_thoroughness = pd.read_csv(
            f'{COMPOSITE_DIR}/coco_throughness.csv', sep=';')
        image_caption_pairs_coco_thoroughness = composite_data_cleaning(
            image_caption_pairs_coco_thoroughness)
        for _, row in image_caption_pairs_coco_correctness.iterrows():
            image_dir = os.path.basename(row['Input.image_url'])
            ref = [row['Input.text1'], row['Input.text2'],
                   row['Input.text3'], row['Input.text4']]
            for i in range(4):
                images.append(f'{MSCOCO_DIR}/val2014/{image_dir}')
                candidates.append(row[f'Input.text{i + 1}'])
                human_scores.append(row[f'Answer.Q{i + 1}Answer'])
                refs.append(ref)
        # for _, row in image_caption_pairs_coco_thoroughness.iterrows():
        #     image_dir_long = row['Input.image_url']
        #     image_dir = os.path.basename(image_dir_long)
        #     ref = [row['Input.text1'], row['Input.text2'], row['Input.text3'], row['Input.text4']]
        #     for i in range(4):
        #         images.append(f'{MSCOCO_DIR}/val2014/{image_dir}')
        #         row_correctness = image_caption_pairs_coco_correctness.loc[
        #             image_caption_pairs_coco_correctness['Input.image_url'] == image_dir_long].to_numpy()
        #         if row_correctness.size == 0:
        #             break
        #         # print(row_correctness[0][i * 2 + 2])
        #         candidates.append(row[f'Input.text{i + 1}'])
        #         human_scores.append(
        #             (float(row[f'Answer.Q{i + 1}Answer']) + float(row_correctness[0][i * 2 + 2])))
        #         refs.append(ref)

        # flickr8k part of composite
        image_caption_pairs_8k_correctness = pd.read_csv(
            f'{COMPOSITE_DIR}/8k_correctness.csv', sep=';')
        image_caption_pairs_8k_correctness = composite_data_cleaning(
            image_caption_pairs_8k_correctness)
        image_caption_pairs_8k_thoroughness = pd.read_csv(
            f'{COMPOSITE_DIR}/8k_throughness.csv', sep=';')
        image_caption_pairs_8k_thoroughness = composite_data_cleaning(
            image_caption_pairs_8k_thoroughness)
        for _, row in image_caption_pairs_8k_correctness.iterrows():
            image_dir = os.path.basename(row['Input.image_url'])
            ref = [row['Input.text1'], row['Input.text2'], row['Input.text3']]
            for i in range(3):
                images.append(f'{FLICKR8K_DIR}/Flicker8k_Dataset/{image_dir}')
                candidates.append(row[f'Input.text{i + 1}'])
                human_scores.append(row[f'Answer.Q{i + 1}Answer'])
                refs.append(ref)
        # for _, row in image_caption_pairs_8k_thoroughness.iterrows():
        #     image_dir_long = row['Input.image_url']
        #     image_dir = os.path.basename(image_dir_long)
        #     ref = [row['Input.text1'], row['Input.text2'], row['Input.text3']]
        #     for i in range(3):
        #         images.append(f'{FLICKR8K_DIR}/Flicker8k_Dataset/{image_dir}')
        #         row_correctness = image_caption_pairs_8k_correctness.loc[
        #             image_caption_pairs_8k_correctness['Input.image_url'] == image_dir_long].to_numpy()
        #         if row_correctness.size == 0:
        #             break
        #         # print(row_correctness[0][i * 2 + 2])
        #         candidates.append(row[f'Input.text{i + 1}'])
        #         # print(row_correctness)
        #         human_scores.append(
        #             (float(row[f'Answer.Q{i + 1}Answer']) + float(row_correctness[0][i * 2 + 2])) / 2)
        #         refs.append(ref)
        print(f'Loaded {len(images)} images')

    elif dataset == 'flickr8k-cf':
        with open(input_json, 'r') as fb:
            data = json.load(fb)
        for v in data.values():
            for d in v:
                images.append(image_directory + d['image_path'])
                candidates.append(d['caption'])
                human_scores.append(float(d['rating']))
                refs.append([' '.join(gt.split()) for gt in v['ground_truth']])

    elif dataset == 'flickr30k':
        dataset_path = '/share/cuvl/image_caption_metrics/flickr30k/flickr30k-images'
        with open('/share/cuvl/image_caption_metrics/flickr30k_test.txt', 'r') as fb:
            for line in fb:
                image = line.strip()
                images.append(dataset_path+'/'+image + '.jpg')
                ref_path = '/share/cuvl/image_caption_metrics/flickr30k_sentences/' + image + '.txt'
                ref = []
                with open(ref_path, 'r') as f2:
                    for raw in f2:
                        splitted = raw.split(' ')
                        processed = []
                        for s in splitted:
                            if '[' in s:
                                continue
                            else:
                                processed.append(
                                    s.replace(']', '').replace('\n', ''))
                        ref.append(' '.join(processed))
                refs.append(ref)

    elif dataset == 'mscoco':
        with open('/share/cuvl/image_caption_metrics/MSCOCO_VAL2014/annotations/captions_val2014.json', 'r') as fb:
            caption_dicts = json.load(fb)['annotations']
        with open('/share/cuvl/image_caption_metrics/MSCOCO_VAL2014/annotations/coco_test_ids.npy', 'rb') as fb:
            test_ids = set(np.load(fb))
        image2caption = {}
        for d in caption_dicts:
            image = d['image_id']
            if not d['id'] in test_ids:
                continue
            if not image in image2caption:
                image2caption[image] = []
            cap = d['caption'].strip().split(' ')
            cap = ' '.join(cap)
            image2caption[image].append(cap)
        for image, captions in image2caption.items():
            images.append('/share/cuvl/image_caption_metrics/MSCOCO_VAL2014/val2014/COCO_val2014_' +
                          str(image).rjust(12, '0')+'.jpg')
            refs.append(captions)

    # images = images[:1000]
    # refs = refs[:1000]
    print(len(images))

    if model_name in ['bleu4', 'bleu1', 'cider']:
        pass
   
    else:
        if model_name == 'first' or model_name == 'first_ref':
            model = clipscore.FirstCLIPScore()
            # model = torch.load('FirstCLIP.pt')
            # model.image_constant = model.image_constant.to(device)
            # model.text_constant = model.text_constant.to(device)
        elif model_name == 'regular' or model_name == 'regular_ref':
            model = clipscore.OriginalCLIPScore()
        model.to(device)
        if args.dataset == "mscoco":
            ckpt_name = "cocoCLIP"
        elif args.dataset == "flickr30k":
            ckpt_name = "flickr30Clip"
        print(f"Loaded ckpt {ckpt_name}")
        model.clip = torch.load(f'{ckpt_name}.pt')

        if args.retrieval == 'True':
            print('====> Doing Retrieval')
            compute_retrieval(model, images, refs, device)
            return

    if dataset == 'pascal':
        get_ref_score = "ref" in model_name
        hc_acc, hi_acc, hm_acc, mm_acc, mean = \
            clipscore.get_clip_score_pascal(model, device, get_ref_score)
        # print(
        #     f"CLIPScore Pascal: {model_name=}: {hc_acc=:.3f}, {hi_acc=:.3f}, {hm_acc=:.3f}, {mm_acc=:.3f}, {mean=:.3f}")
    else:
        if model_name in ['bleu1', 'bleu4', 'cider']: 
            per_instance_image_text = []
            results = other_metrics.get_all_metrics(refs, candidates)[model_name]
            if model_name == 'bleu4':
                results = results[-1]
            per_instance_image_text = results
            print(len(per_instance_image_text))
        elif not 'ref' in model_name:
            # print('Using get clip score')
            _, per_instance_image_text, candidate_feats = clipscore.get_clip_score(
                model, images, candidates, device, refs)    
        else:
            _, per_instance_image_text, candidate_feats = clipscore.get_clip_score_ref(
                model, images, candidates, refs, device)
        print('CLIPScore Tau-{}: {:.3f}'.format(tauvariant, 100 *
                                                scipy.stats.kendalltau(per_instance_image_text, human_scores, variant=tauvariant)[0], nan_policy='omit'))

    if model_name == 'first' and args.stage == 'train':
        torch.save(model, 'FirstCLIP.pt')

@progress_alerts(func_name="compute metrics")
def main(args):
    print(f'{args.dataset} (Tau-c)')
    if args.dataset == 'flickr8k-expert':
        compute_human_correlation(args.model, f'{FLICKR8K_DIR}/flickr8k.json',
                                  f'{FLICKR8K_DIR}/', tauvariant='c', args=args)
    elif args.dataset == 'thumb':
        compute_human_correlation(args.model,  f'{MSCOCO_DIR}/THumB/mscoco/mscoco_THumB-1.0.jsonl',
                                  f'{MSCOCO_DIR}/val2014/', 'thumb', tauvariant='c', args=args)
    elif args.dataset == 'pascal':
        compute_human_correlation(args.model, f'{PASCAL_DIR}/pascal50S.mat',
                                  str(PASCAL_DIR), 'pascal', args=args)
    elif args.dataset == 'composite':
        compute_human_correlation(
            args.model, None, None, 'composite', tauvariant='c', args=args)

    elif args.dataset == 'flickr8k-cf':
        compute_human_correlation(
            args.model, f'{FLICKR8K_DIR}/crowdflower_flickr8k.json', f'{FLICKR8K_DIR}/', tauvariant='b', args=args)

    # dummy arguments
    elif args.dataset == 'flickr30k':
        compute_human_correlation(
            args.model, None, None, 'flickr30k', tauvariant='c', args=args)

    elif args.dataset == 'mscoco':
        compute_human_correlation(
            args.model, None, None, 'mscoco', tauvariant='c', args=args)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default="flickr8k-expert", choices=["flickr8k-expert",
                                                                         "thumb", "pascal", "composite", "flickr8k-cf", "flickr30k", "mscoco"], type=str)
    parser.add_argument('--model', default='first',
                        choices=['regular', 'first', 'regular_ref', 'first_ref', 'bleu1', 'bleu4', 'cider'], type=str)
    parser.add_argument('--stage', default='eval',
                        choices=['train', 'eval'], type=str)
    parser.add_argument('--retrieval', default='False',
                        choices=['False', 'True'], type=str)
    args = parser.parse_args()
    main(args)
