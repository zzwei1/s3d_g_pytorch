import torch
import torch.nn as nn
import ipdb

class BasicConv3d(nn.Module):
    def __init__(self, 
                 in_channel, 
                 out_channel, 
                 kernel_size=1, 
                 stride=1, 
                 padding=0, 
                 use_bias=False,
                 use_bn=True,
                 activation='rule'):
        super(BasicConv3d, self).__init__()

        self.use_bn = use_bn
        self.activation = activation
        self.conv3d = nn.Conv3d(in_channel, out_channel, kernel_size=kernel_size,
                                     stride=stride, padding=padding, bias=use_bias)
        if use_bn:
            self.bn = nn.BatchNorm3d(out_channel, eps=1e-3, momentum=0.001, affine=True)
        if activation == 'rule':
            self.activation = nn.ReLU()

    def forward(self, x):
        x = self.conv3d(x)
        if self.use_bn:
            x = self.bn(x)
        if self.activation is not None:
            x = self.activation(x)
        # ipdb.set_trace()
        return x

class sep_conv(nn.Module):
    def __init__(self, 
                 in_channel, 
                 out_channel, 
                 kernel_size, 
                 stride=1, 
                 padding=0, 
                 use_bias=True,
                 use_bn=True,
                 activation='rule'):
        super(sep_conv, self).__init__()
        down = BasicConv3d(in_channel, out_channel, (1,kernel_size,kernel_size), stride=stride,
                                padding=(0,padding,padding), use_bias=False, use_bn=True)
        up = BasicConv3d(out_channel, out_channel, (kernel_size,1,1), stride=1,
                                padding=(padding,0,0), use_bias=False, use_bn=True)
        self.sep_conv = nn.Sequential(down, up)

    def forward(self, x):
        x = self.sep_conv(x)
        # ipdb.set_trace()
        return x

class sep_inc(nn.Module):
    def __init__(self, in_channel, out_channel):
        super(sep_inc, self).__init__()
        # branch 0
        self.branch0 = BasicConv3d(in_channel, out_channel[0], kernel_size=(1,1,1), stride=1, padding=0)
        # branch 1
        branch1_conv1 = BasicConv3d(in_channel, out_channel[1],kernel_size=(1,1,1), stride=1, padding=0)
        branch1_sep_conv = sep_conv(out_channel[1], out_channel[2], kernel_size=3, stride=1, padding=1)
        self.branch1 = nn.Sequential(branch1_conv1, branch1_sep_conv)
        # branch 2  
        branch2_conv1 = BasicConv3d(in_channel, out_channel[3],kernel_size=(1,1,1), stride=1, padding=0)
        branch2_sep_conv = sep_conv(out_channel[3], out_channel[4], kernel_size=3, stride=1, padding=1)
        self.branch2 = nn.Sequential(branch2_conv1, branch2_sep_conv)
        # branch 3
        branch3_pool = nn.MaxPool3d(kernel_size=3, stride=1, padding=1)     
        branch3_conv = BasicConv3d(in_channel, out_channel[5], kernel_size=(1,1,1))
        self.branch3 = nn.Sequential(branch3_pool, branch3_conv)

    def forward(self, x):
        # ipdb.set_trace()
        out_0 = self.branch0(x)
        out_1 = self.branch1(x)
        out_2 = self.branch2(x)
        out_3 = self.branch3(x)
        out = torch.cat((out_0, out_1, out_2, out_3), 1)
        return out


class S3D_G(nn.Module):
    def __init__(self, num_class=400, drop_prob=0.5, in_channel=3 ):
        super(S3D_G, self).__init__()
        self.feature = nn.Sequential(
            sep_conv(in_channel, 64, kernel_size=7, stride=2, padding=3),       # (64,32,112,112)
            nn.MaxPool3d(kernel_size=(1,3,3), stride=(1,2,2), padding=(0,1,1)), # (64,32,56,56)
            BasicConv3d(64, 64, kernel_size=1, stride=1),                       # (64,32,56,56)
            sep_conv(64, 192, kernel_size=3, stride=1, padding=1),              # (192,32,56,56)
            nn.MaxPool3d(kernel_size=(1,3,3), stride=(1,2,2), padding=(0,1,1)), # (192,32,28,28)
            sep_inc(192, [64,96,128,16,32,32]),                                 # (256,32,28,28)
            sep_inc(256, [128,128,192,32,96,64]),                               # (480,32,28,28)
            nn.MaxPool3d(kernel_size=(3,3,3), stride=(2,2,2), padding=(1,1,1)), # (480,16,14,14)
            sep_inc(480, [192, 96, 208, 16, 48, 64]),                           # (512,16,14,14)
            sep_inc(512, [160, 112, 224, 24, 64, 64]),                          # (512,16,14,14)
            sep_inc(512, [128, 128, 256, 24, 64, 64]),                          # (512,16,14,14)
            sep_inc(512, [112, 144, 288, 32, 64, 64]),                          # (528,16,14,14)
            sep_inc(528, [256, 160, 320, 32, 128, 128]),                        # (832,16,14,14)
            nn.MaxPool3d(kernel_size=(2,2,2),stride=(2,2,2),padding=(0,0,0)),   # (832,8,7,7)
            sep_inc(832, [256, 160, 320, 32, 128, 128]),                        # (832,8,7,7)
            sep_inc(832, [384, 192, 384, 48, 128, 128]),                        # (1024,8,7,7) 
            nn.AvgPool3d(kernel_size=(2, 7, 7), stride=1),                      # (1024,7,1,1)
            nn.Dropout3d(drop_prob),
            nn.Conv3d(1024, num_class, kernel_size=1, stride=1, bias=True),     # (num_class,7,1,1)
        )
        self.softmax = nn.Softmax(1)

    def forward(self, x):
        # ipdb.set_trace()
        out = self.feature(x)               # (batch_size,num_class,7,1,1)
        # squeeze the spatial dimension
        out = out.squeeze(3)                # (batch_size,num_class,7,1)
        out = out.squeeze(3)                # (batch_size,num_class,7)
        out = out.mean(2)                   # (batch_size,num_class)
        prediction = self.softmax(out)

        return  prediction

if __name__ == "__main__":
    model = S3D_G()
    x = torch.rand((1,3,64,224,224))
    p, out = model(x)