# -*- coding: utf-8 -*-

import json
import sys
import math
import random
from itertools import chain

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

from io_common import FileProgressingbar, generate_lineidx, img_from_base64
from tsv_io import TSVFile

NUM_FRAMES = 10


class VolleyballDataset(Dataset):
    def __init__(self, phase, frame_mode):
        self.phase = phase
        if frame_mode == 'target-frame':
            TRAINVAL_PATH = './data/feature drop-0.2 trainval.tsv'
            TEST_PATH = './data/feature drop-0.2 test.tsv'
        elif frame_mode == 'frames':
            TRAINVAL_PATH = './data/feature frames drop-0.2 trainval.tsv'
            TEST_PATH = './data/feature frames drop-0.2 test.tsv'
        else:
            print('wrong frame mode')
            sys.exit(0)

        if phase == 'trainval':
            self.tsv_path = TRAINVAL_PATH
        elif phase == 'test':
            self.tsv_path = TEST_PATH
        else:
            print('wrong dataset phase')
            sys.exit(0)

        self.tsv = TSVFile(self.tsv_path)

    def __getitem__(self, idx):
        row = self.tsv.seek(idx)
        json_dict = json.loads(row[0])

        group_info = torch.tensor(json_dict['group_info'])
        actions = torch.tensor(
            json_dict['actions']).view(-1).repeat(NUM_FRAMES)
        # actions = torch.tensor(json_dict['actions']).repeat(NUM_FRAMES)
        activities = torch.tensor(json_dict['activities']).repeat(NUM_FRAMES)
        features = torch.tensor(json_dict['featuers'])

        return group_info, actions, activities, features

    def __len__(self):
        return self.tsv.num_rows()