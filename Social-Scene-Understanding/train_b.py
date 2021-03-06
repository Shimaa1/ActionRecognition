# training script for neural nets
import argparse
import copy
import math
import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from inception import inception_v3
# TODO:
from model import ClassifierB
from torch.utils.data.dataloader import DataLoader
from volleyball_loader_b import VolleyballDataset
import pickle

device_ids = [0]
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

# hyperparameters
__BATCH_SIZE = 4
__NUM_EPOCHS = 50
__LEARNING_RATE = 1e-5
__WEIGHT_DECAY = 0.00004
__DROPOUT_RATIO = 0.2
__OUTPUT_HEIGHT = 87
__OUTPUT_WIDTH = 157
__CROP_SIZE = 5
__CHANNEL = 1056
__BBOX_NUM = 12
__CLASSIFIER_INPUT = __CHANNEL * __CROP_SIZE * __CROP_SIZE
__EMBED_DIM = 2048
__ACTION_WEIGHT = torch.tensor([1., 1., 2., 3., 1., 2., 2., 0.2,
                                1.]).to(device)
__ACTIONS_LOSS_WEIGHT = 0.5
__TIME_STEP = 10
__TEST_GAP = 1
__STORE_GAP = 1
__OLD_CLASSIFIERA_PATH = './models/classifier/classifierA lr-1e-05 weight_decay-4e-05 crop_size-5 embed_dim-2048 epoch-26 dropout_ratio-0.2.pth'
__OLD_CLASSIFIERB_PATH = './models/classifier/classifierB-atten mixed featue lr-1e-05 weight_decay-4e-05 crop_size-5 embed_dim-2048 dropout_ratio-0.2 epoch-2.pth'
__CLASSIFIER_PATH = './models/classifier/'

note = "implement social scene  \n\
        time: {}   \n\
        lr: {}  \n\
        weight_decay: {}    \n\
        crop_size: {}   \n\
        embed_dim: {}   \n\
        dropout_ratio:{} \n".format(
    time.strftime('%m-%d %H:%M:%S', time.localtime(time.time())),
    __LEARNING_RATE, __WEIGHT_DECAY, __CROP_SIZE, __EMBED_DIM, __DROPOUT_RATIO)

__LOG_PATH = './log/B1-atten mixed feature lr-{} weight_decay-{} crop_size-{} embed_dim-{} drpout_ratio-{}.txt'.format(
    __LEARNING_RATE, __WEIGHT_DECAY, __CROP_SIZE, __EMBED_DIM, __DROPOUT_RATIO)

PACTIONS = [
    'blocking', 'digging', 'falling', 'jumping', 'moving', 'setting',
    'spiking', 'standing', 'waiting'
]
__PACTION_NUM = 9

GACTIVITIES = [
    'r_set', 'r_spike', 'r-pass', 'r_winpoint', 'l_set', 'l-spike', 'l-pass',
    'l_winpoint'
]
__GACTIVITY_NUM = 8

id2pact = {i: name for i, name in enumerate(PACTIONS)}
id2gact = {i: name for i, name in enumerate(GACTIVITIES)}


def collate_fn(batch):
    group_info, actions, activities, features = zip(*batch)
    return torch.cat(features, dim=0), torch.cat(
        actions, dim=0), np.concatenate(activities,
                                        axis=0), torch.cat(group_info, dim=0)


def train_model(classifierB, dataloaders_dict, criterion_dict, optimizer):
    since = time.time()

    with open(__LOG_PATH, 'a') as f:
        f.write('=================================================\n')
        f.write('{}\n'.format(note))
        f.write('=================================================\n')

    for epoch in range(__NUM_EPOCHS):
        print('Epoch {}/{}'.format(epoch + 3, __NUM_EPOCHS))
        print('-' * 10)

        # # TODO:
        if (epoch + 1) % __TEST_GAP != 0 or epoch == 0:
            phases = ['trainval']
        else:
            phases = ['trainval', 'test']
        # phases = ['trainval']

        for phase in phases:
            total_action_loss = 0.0
            total_activity_loss = 0.0

            total_actions_accuracy = 0.0
            activities_accuracy = 0.0

            action_len = 0.0
            activity_len = 0.0
            total_len = 0.0
            if phase == 'trainval':
                classifierB.train()
            else:
                classifierB.eval()

            for features, actions, activities, group_info in dataloaders_dict[
                    phase]:
                action_loss = 0.0
                activity_loss = 0.0

                with torch.set_grad_enabled(phase == 'trainval'):
                    batch_size = activities.shape[0] / __TIME_STEP
                    # actions = torch.tensor(actions).to(device)
                    actions = actions.view(-1).to(device)
                    activities = torch.tensor(activities).to(device)

                    action_logits, activity_logits = classifierB(features)

                    action_loss = criterion_dict['action'](
                        action_logits,
                        actions) / (batch_size * __TIME_STEP * __BBOX_NUM)
                    activity_loss = criterion_dict['activity'](
                        activity_logits,
                        activities) / (batch_size * __TIME_STEP)

                    total_loss = __ACTIONS_LOSS_WEIGHT * action_loss + activity_loss

                    if phase == 'trainval':
                        optimizer.zero_grad()
                        total_loss.backward()
                        optimizer.step()

                    _, actions_labels = torch.max(action_logits, 1)
                    _, activities_labels = torch.max(activity_logits, 1)

                    total_action_loss += action_loss
                    total_activity_loss += activity_loss

                    total_actions_accuracy += torch.sum(
                        actions_labels == actions.data)
                    activities_accuracy += torch.sum(
                        activities_labels == activities.data)

                    action_len += batch_size * __TIME_STEP * __BBOX_NUM
                    activity_len += batch_size * __TIME_STEP
                    total_len += 1

                    print('{} {} Person Loss: {:.4f} Acc: {:.4f}'.format(
                        epoch + 3, phase, total_action_loss / total_len,
                        total_actions_accuracy.double() / action_len))

                    print('{} {} Group Loss: {:.4f} Acc: {:.4f}'.format(
                        epoch + 3, phase, total_activity_loss / total_len,
                        activities_accuracy.double() / activity_len))

            epoch_action_loss = total_action_loss / total_len
            epoch_action_acc = total_actions_accuracy.double() / action_len

            epoch_activity_loss = total_activity_loss / total_len
            epoch_activity_acc = activities_accuracy.double() / activity_len

            print('|{}|{}|'.format(
                time.strftime('%m-%d %H:%M:%S', time.localtime(since)),
                time.strftime('%m-%d %H:%M:%S', time.localtime(time.time()))))
            print('{} {} Person Loss: {:.4f} Acc: {:.4f}'.format(
                epoch + 3, phase, epoch_action_loss, epoch_action_acc))
            print('{} {} Group Loss: {:.4f} Acc: {:.4f}'.format(
                epoch + 3, phase, epoch_activity_loss, epoch_activity_acc))

            with open(__LOG_PATH, 'a') as f:
                f.write('|{}|{}|'.format(
                    time.strftime('%m-%d %H:%M:%S', time.localtime(since)),
                    time.strftime('%m-%d %H:%M:%S',
                                  time.localtime(time.time()))))
                f.write('{} {} Person Loss: {:.4f} Acc: {:.4f} \n'.format(
                    epoch + 3, phase, epoch_action_loss, epoch_action_acc))
                f.write('|{}|{}|'.format(
                    time.strftime('%m-%d %H:%M:%S', time.localtime(since)),
                    time.strftime('%m-%d %H:%M:%S',
                                  time.localtime(time.time()))))
                f.write('{} {} Group Loss: {:.4f} Acc: {:.4f} \n'.format(
                    epoch + 3, phase, epoch_activity_loss, epoch_activity_acc))

            if (epoch + 1) % __STORE_GAP == 0:
                torch.save(
                    classifierB.module.state_dict(), __CLASSIFIER_PATH +
                    'classifierB1-atten mixed feature lr-{} weight_decay-{} crop_size-{} embed_dim-{} dropout_ratio-{} epoch-{}.pth'
                    .format(__LEARNING_RATE, __WEIGHT_DECAY, __CROP_SIZE,
                            __EMBED_DIM, __DROPOUT_RATIO, epoch + 3))

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    with open(__LOG_PATH, 'a') as f:
        f.write('Training complete in {:.0f}m {:.0f}s\n'.format(
            time_elapsed // 60, time_elapsed % 60))


def main():
    print('creating classifierB')
    classifierB = ClassifierB(feature_dim=__CLASSIFIER_INPUT,
                              embed_dim=__EMBED_DIM,
                              dropout_ratio=__DROPOUT_RATIO).to(device)

    # pretrained_dict = torch.load(__OLD_CLASSIFIERA_PATH)
    # classifierB_dict = classifierB.state_dict()

    # pretrained_dict = {
    #     k: v
    #     for k, v in pretrained_dict.items()
    #     if k in ['embed_layer.0.weight', 'embed_layer.0.bias']
    # }
    # classifierB_dict.update(pretrained_dict)
    # print('classifierB loading {}\nfrom {}'.format(pretrained_dict.keys(), __OLD_CLASSIFIERA_PATH))
    # classifierB.load_state_dict(classifierB_dict)

    classifierB.load_state_dict(torch.load(__OLD_CLASSIFIERB_PATH))

    classifierB = nn.DataParallel(classifierB, device_ids=device_ids)

    dataloaders_dict = {
        x: DataLoader(VolleyballDataset(x),
                      batch_size=__BATCH_SIZE,
                      shuffle=True,
                      num_workers=2,
                      collate_fn=collate_fn)
        for x in ['trainval', 'test']
        # for x in ['trainval']
    }
    criterion_dict = {
        'action': nn.CrossEntropyLoss(weight=__ACTION_WEIGHT),
        'activity': nn.CrossEntropyLoss()
    }

    optimizer = optim.Adam(classifierB.parameters(),
                           lr=__LEARNING_RATE,
                           weight_decay=__WEIGHT_DECAY)

    train_model(classifierB, dataloaders_dict, criterion_dict, optimizer)


if __name__ == "__main__":
    main()
