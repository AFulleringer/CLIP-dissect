import os
import argparse
import datetime
import json
import pandas as pd
import torch

import utils
import similarity


parser = argparse.ArgumentParser(description='CLIP-Dissect')

parser.add_argument("--clip_model", type=str, default="ViT-B/16", 
                    choices=['RN50', 'RN101', 'RN50x4', 'RN50x16', 'RN50x64', 'ViT-B/32', 'ViT-B/16', 'ViT-L/14'],
                   help="Which CLIP-model to use")
parser.add_argument("--target_model", type=str, default="resnet50", 
                   help=""""Which model to dissect, supported options are pretrained imagenet models from
                        torchvision and resnet18_places""")
parser.add_argument("--target_layers", type=str, default=["features[0]", "features[3]", "features[6]", "features[8]", "features[10]"],
                    help="Which layer activations to look at. Following the naming scheme of the PyTorch module used")
parser.add_argument("--d_probe", type=str, default="broden", 
                    choices = ["imagenet_broden", "cifar100_val", "imagenet_val", "broden", "imagenet_broden"])
parser.add_argument("--concept_set", type=str, default="data/20k.txt", help="Path to txt file containing concept set")
parser.add_argument("--batch_size", type=int, default=200, help="Batch size when running CLIP/target model")
parser.add_argument("--device", type=str, default="cuda", help="whether to use GPU/which gpu")
parser.add_argument("--activation_dir", type=str, default="saved_activations", help="where to save activations")
parser.add_argument("--result_dir", type=str, default="results", help="where to save results")
parser.add_argument("--pool_mode", type=str, default="avg", help="Aggregation function for channels, max or avg")
parser.add_argument("--similarity_fn", type=str, default="soft_wpmi", choices=["soft_wpmi", "wpmi", "rank_reorder", 
                                                                               "cos_similarity", "cos_similarity_cubed"])
parser.add_argument("--run_name", type=str, default=None)
parser.parse_args()
if __name__ == '__main__':
    args = parser.parse_args()
    similarity_fn = eval("similarity.{}".format(args.similarity_fn))

    utils.save_activations(clip_name = args.clip_model, target_name = args.target_model, 
                           target_layers = args.target_layers, d_probe = args.d_probe, 
                           concept_set = args.concept_set, batch_size = args.batch_size, 
                           device = args.device, pool_mode=args.pool_mode, 
                           save_dir = args.activation_dir)
    
    outputs = {"layer":[], "unit":[], "description":[], "similarity":[]}
    with open(args.concept_set, 'r') as f: 
        words = (f.read()).split('\n')
    
    for target_layer in args.target_layers:
        save_names = utils.get_save_names(clip_name = args.clip_model, target_name = args.target_model,
                                  target_layer = target_layer, d_probe = args.d_probe,
                                  concept_set = args.concept_set, pool_mode = args.pool_mode,
                                  save_dir = args.activation_dir)
        target_save_name, clip_save_name, text_save_name = save_names

        similarities = utils.get_similarity_from_activations(
            target_save_name, clip_save_name, text_save_name, similarity_fn, return_target_feats=False, device=args.device
        )
        vals, ids = torch.max(similarities, dim=1)
        
        del similarities
        torch.cuda.empty_cache()
        
        descriptions = [words[int(idx)] for idx in ids]
        
        outputs["unit"].extend([i for i in range(len(vals))])
        outputs["layer"].extend([target_layer]*len(vals))
        outputs["description"].extend(descriptions)
        outputs["similarity"].extend(vals.cpu().numpy())
        
    df = pd.DataFrame(outputs)
    if not os.path.exists(args.result_dir):
        os.mkdir(args.result_dir)
    save_name = args.target_model.split('/')[-2]
    if args.run_name is not None:
        save_name = save_name + f'_{args.run_name}'
    save_path = "{}/{}_{}".format(args.result_dir, save_name, datetime.datetime.now().strftime("%y_%m_%d_%H_%M"))
    os.mkdir(save_path)
    df.to_csv(os.path.join(save_path, f"descriptions_{save_name}.csv"), index=False)
    with open(os.path.join(save_path, "args.txt"), 'w') as f:
        json.dump(args.__dict__, f, indent=2)
print('Done!')
print(f'saving results to: {save_path}')