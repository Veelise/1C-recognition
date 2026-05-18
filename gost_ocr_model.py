import torch
from torch import nn
from torch.nn import functional as F


class BidirectionalLSTM(nn.Module):
    def __init__(self, n_in, n_hidden, n_out):
        super().__init__()
        self.rnn = nn.LSTM(n_in, n_hidden, bidirectional=True)
        self.linear = nn.Linear(n_hidden * 2, n_out)

    def forward(self, x):
        recurrent, _ = self.rnn(x)
        t, b, h = recurrent.size()
        output = self.linear(recurrent.view(t * b, h))
        return output.view(t, b, -1)


class CRNN(nn.Module):
    def __init__(self, img_h, num_channels, num_classes, hidden_size=256):
        super().__init__()
        assert img_h % 16 == 0, "img_h should be a multiple of 16"

        self.cnn = nn.Sequential(
            nn.Conv2d(num_channels, 64, 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(64, 128, 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),

            nn.Conv2d(128, 256, 3, 1, 1),
            nn.BatchNorm2d(256),
            nn.ReLU(True),
            nn.Conv2d(256, 256, 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d((2, 2), (2, 1), (0, 1)),

            nn.Conv2d(256, 512, 3, 1, 1),
            nn.BatchNorm2d(512),
            nn.ReLU(True),
            nn.Conv2d(512, 512, 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d((2, 2), (2, 1), (0, 1)),

            nn.Conv2d(512, 512, 2, 1, 0),
            nn.ReLU(True),
        )

        self.rnn = nn.Sequential(
            BidirectionalLSTM(512, hidden_size, hidden_size),
            BidirectionalLSTM(hidden_size, hidden_size, num_classes),
        )
        self._init_output_head()

    def _init_output_head(self):
        # Снижаем стартовую склонность модели предсказывать blank везде.
        output_linear = self.rnn[-1].linear
        if output_linear.bias is not None:
            nn.init.zeros_(output_linear.bias)
            output_linear.bias.data[0] = -3.0

    def forward(self, x):
        conv = self.cnn(x)
        b, c, h, w = conv.size()
        if h != 1:
            conv = F.adaptive_avg_pool2d(conv, (1, w))
        conv = conv.squeeze(2)
        conv = conv.permute(2, 0, 1)
        return self.rnn(conv)
