# Crash Catcher: DashCam Accident Detector  # DashCam 사고 감지기

## we want any plots to show up in the notebook
get_ipython().magic(u'matplotlib inline')
## has the usual packages I use
get_ipython().magic(u'run startup')
import numpy
import os
import re
import pickle
import timeit
import glob
import cv2

from skimage import transform
import skimage
from skimage import io

import sklearn
from sklearn.model_selection import train_test_split   ### import sklearn tool

import keras
from keras.preprocessing import image as image_utils
from keras.callbacks import ModelCheckpoint

rcdefaults()  ### set the defaults
matplotlib.rc('font',family='Bitstream Vera Serif')   ### I like my plots to look a certain way :)


# 먼저 파일에서 비디오 (.mp4 형식, 크기가 720x1280)로로드 할 함수를 작성하십시오.
# 비디오의 각 프레임은 처리 할 수있는 이미지로 변환됩니다.
# 프로세스를 (최소한으로) 메모리 집약적으로 만들기 위해 이미지를 144 x 256 픽셀 크기로 다운 스케일합니다. 또한 이미지는 원래 RGB 색상이기 때문에,
# 우리는 그레이 스케일로 변환한다. 이것은 또한 메모리의 양을 줄이고, 유용한 정보가 손실 될 수는 있지만 장면에서 장면으로의 색상 변화 (또는 dashcam에서 dashcam까지)는 덜 중요합니다.
# 또한 색상 차원을 잃으면 5-D 문제가 4-D 문제로 바뀌고 좀 더 다루기 쉽습니다.

### 다음은 분석을 위해 파일에서 비디오로로드하는 함수입니다.

def load_set(videofile):
    '''
	입력은 동영상 파일의 경로입니다. 교육 동영상은 99 프레임이며 해상도는 720x1248입니다.
    이것은 각 비디오에 개별적으로 사용되어 비디오를 배열로 프레임의 시퀀스 / 스택으로 변환합니다
    반환 된 모양 (img)은 99 (프레임 당 비디오), 144 (열당 픽셀 수), 256 (행당 픽셀 수)입니다.
    '''
    ### below, the video is loaded in using VideoCapture function
    vidcap = cv2.VideoCapture(videofile)
    ### now, read in the first frame
    success,image = vidcap.read()
    count = 0       ### start a counter at zero
    error = ''      ### error flag
    success = True  ### start "sucess" flag at True

    img = []        ### create an array to save each image as an array as its loaded 
    while success: ### while success == True
        success, img = vidcap.read()  ### if success is still true, attempt to read in next frame from vidcap video import
        count += 1  ### increase count
        frames = []  ### frames will be the individual images and frames_resh will be the "processed" ones
        for j in range(0,99):
            try:
                success, img = vidcap.read()
                ### conversion from RGB to grayscale image to reduce data
                tmp = skimage.color.rgb2gray(numpy.array(img))
                ### ref for above: https://www.safaribooksonline.com/library/view/programming-computer-vision/9781449341916/ch06.html
                
                ### downsample image
                tmp = skimage.transform.downscale_local_mean(tmp, (5,5))
                frames.append(tmp)
                count+=99
            
            except:
                count+=1
                pass#print 'There are ', count, ' frame; delete last'        read_frames(videofile, name)
    
        ### if the frames are the right shape (have 99 entries), then save
        #print numpy.shape(frames), numpy.shape(all_frames)
        if numpy.shape(frames)==(99, 144, 256):
            all_frames.append(frames)
        ### if not, pad the end with zeros
        elif numpy.shape(frames[0])==(144,256):
            #print shape(all_frames), shape(frames), shape(concatenate((all_frames[-1][-(99-len(frames)):], frames)))
            #print numpy.shape(all_frames), numpy.shape(frames)
            all_frames.append(numpy.concatenate((all_frames[-1][-(99-len(frames)):], frames)))
        elif numpy.shape(frames[0])!=(144,256):
            error = 'Video is not the correct resolution.'
    vidcap.release()
    del frames; del image
    return all_frames, error



# 다음으로, 우리는 훈련 데이터를로드하고 무작위로 훈련과 검증 세트를 선택하고 분리합니다.
# (일부 데이터는 별도로 설정되거나 나중에 테스트하기 위해 포함되지 않음)


img_filepath = '/pathway/to/videos' #### the filepath for the training video set
neg_all = glob.glob(img_filepath + 'negative/*.mp4')               #### negative examples - ACCV
pos_2 = glob.glob(img_filepath + 'positive/*.mp4')                 #### positive examples - ACCV
pos_1 = glob.glob(img_filepath + '../YTpickles/*.pkl')             #### positive examples - youtube
pos_all = concatenate((pos_1, pos_2))

all_files = concatenate((pos_all, neg_all))
print len(neg_all), len(pos_all)                                   #### print check



def label_matrix(values):
    '''transforms labels for videos to one-hot encoding/dummy variables'''
    n_values = numpy.max(values) + 1    ### take max value (that would be 1, because it is a binary classification), 
                                        ### and create n+1 (that would be two) sized matrix
    return numpy.eye(n_values)[values]  ### return matrix with results coded - 1 in first column for no-accident
                                        ### and a 1 in second column for an accident

labels = numpy.concatenate(([1]*len(pos_all), [0]*len(neg_all[0:len(pos_all)])))  ### create the labels for the videos
labels = label_matrix(labels)           ### make the labels into a matrix for the HRNN training



# Load in data from each video and save to (massive) data array -- should be of
# shape (L, 99, 144, 256), where L is the number of files that are going to be used.
# We use a function to load in the data differently depending on whether it is pickled
# (from youtube) or part of the ACCV dataset.
# 각 비디오의 데이터를로드하고 (대량) 데이터 배열에 저장 - 모양 (L, 99, 144, 256)이어야합니다. 여기서 L은 사용할 파일 수입니다.
# 우리는 그것이 (유튜브에서) pickle되거나 ACCV dataset의 일부분에 따라 데이터를 다르게로드하는 함수를 사용합니다.

def make_dataset(rand):
    seq1 = numpy.zeros((len(rand), 99, 144, 256))   ### create an empty array to take in the data
    for i,fi in enumerate(rand):                    ### for each file...
        print (i, fi)                               ### as we go through, print out each one
        if fi[-4:] == '.mp4':
            t = load_set(fi)                        ### load in the video file using previously defined function if .mp4 file
        elif fi[-4:]=='.pkl':
            t = pickle.load(open(fi, 'rb'))         ### otherwise, if it's pickled data, load the pickle
        if shape(t)==(99,144,256):                  ### double check to make sure the shape is correct, and accept
            seq1[i] = t                             ### save image stack to array
        else:# TypeError:
            'Image has shape ', shape(t), 'but needs to be shape', shape(seq1[0]) ### if exception is raised, explain
            pass                                    ### continue loading data
    print (shape(seq1))
    return seq1



# 그런 다음 데이터가 위에서 만든 레이블로 훈련 및 유효성 집합으로 나누어지고 전체 집합 중 60 %가 교육으로 설정되고 20 %는 유효성 검사로 설정됩니다. 
# (데이터의 나머지 20 %는 홀드 아웃 테스트 집합으로 남음)
# 분할 된 부분은 약간 이상하게 보일 수 있지만 유효성 검사 및 테스트 세트가 동일한 크기 (교육 유효성 검사 테스트의 경우 전체 60-20-20)를 보장합니다.

##### split data into training and validation (sets and shuffle)
x_train, x_t1, y_train, y_t1 = train_test_split(all_files, labels, test_size=0.40, random_state=0)  ### split
x_train = array(x_train); y_train = array(y_train)                          ### need to be arrays

x_testA = array(x_t1[len(x_t1)/2:]); y_testA = array(y_t1[len(y_t1)/2:])    #### test set

### valid set for model
x_testB = array(x_t1[:len(x_t1)/2]); y_test = array(y_t1[:len(y_t1)/2])    ### need to be arrays
x_test = make_dataset(x_testB)




# 아래에서, 노이즈 위의 신호가 있는지 확인하기위한 테스트가 수행되었습니다. 
# -- 가짜 데이터가 임의의 숫자에서 생성되어 실제 데이터가 무작위 데이터에서 수집 된 데이터 / 패턴보다 잘 수행되었음을 보여줍니다.
# 고맙게도, 모델은 난수로 실행할 때 겨우 50 %의 정확도에 도달 할 수 있습니다.

#### populate data as random numbers as a sanity check
# 데이터를 무결성 검사로 난수로 채움
#seq3 = zeros((60,99,144,256))
#for j in range(60):   ### for each file...
#    [np.random.random((244,256)) for i in range(99)]    ### save image stack to array
#print (shape(seq3))              ### print check

#x_train2, x_test2, y_train2, y_test2 = train_test_split(seq3, labels, test_size=0.2, random_state=0)  ### split
#x_train2 = array(x_train2); y_train2 = array(y_train2)     ### need to be arrays
#x_test2 = array(x_test2); y_test2 = array(y_test2)         ### need to be arrays




# 아래에서 HRNN은 열차 및 유효성 검사 세트에서 실행되도록 설정됩니다. 

### 코드는 다음 리소스에서 크게 재 작업됩니다.  # 케라스 공식 문서
### https://github.com/fchollet/keras/blob/master/examples/mnist_hierarchical_rnn.py
### https://keras.io/examples/mnist_hierarchical_rnn/ 
"""
# HRNN : 계층적 RNN
HRNN은 복잡한 시퀀스에 대해 여러 단계의 시간 내 검색을 통해 학습 할 수 있습니다.
일반적으로, HRNN의 제 1 반복 층은 시간 - 의존 비디오 (예를 들어, 이미지들의 세트)벡터로.
그 다음, 제 2 반복 층은 이들 벡터 (제 1 층에 의해 부호화 됨)를 제 2 층으로 부호화한다.

첫 번째 LSTM 계층은 먼저 모양 (240, 1)의 픽셀의 모든 열을 모양 (128,)의 열 벡터로 인코딩합니다.
두 번째 LSTM 레이어는 240 개의 열 벡터 (240, 128)를 전체 이미지를 나타내는 이미지 벡터로 인코딩합니다.
최종 밀도 레이어가 예측을 위해 추가됩니다.
"""
import keras
from keras.models import Model
from keras.layers import Input, Dense, TimeDistributed
from keras.layers import LSTM

### 하이퍼파라미터 설정 (사전정의 데이터)
batch_size = 15
num_classes = 2  # 분류갯수
epochs = 30

### number of hidden layers in each NN  # 각각 히든 레이어의 수
row_hidden = 128
col_hidden = 128

### print basic info  # 기본 정보 출력
print('x_train shape:', x_train.shape)
print(x_train.shape[0], 'train samples')
print(x_test.shape[0], 'test samples')

### get shape of rows/columns for each image  # 각 이미지에 대한 행/열의 모양 가져오기
frame, row, col = (99, 144, 256)

### 4D input - for each 3-D sequence (of 2-D image) in each video (4th)
# 4D 입력 - 각 비디오의 각 3D 시퀀스 (2 차원 이미지)에 대해 (4 번째)
x = Input(shape=(frame, row, col))

# TimeDistributed Wrapper를 사용하여 픽셀 행을 인코딩합니다.
encoded_rows = TimeDistributed(LSTM(row_hidden))(x)
# TimeDistributed() : 3차원 텐서 입력을 받도록 레이어를 확장(?) <- 확실한 건 출력 혹은 입력 형태(차원)를 변환 시킴
# (x)는 LSTM의 입력 형태인거 같으나 (?) 파이썬 이해 부족으로 명확하지 않음
# ** LSTM(메모리 셀의 개수, input_dim=입력속성의 수, input_length=시퀀스데이터의 입력 길이)  <- Dense()같은 레이어
#		-> 메모리 셀의 개수 : 기억용량 정도와 출력 형태를 결정 지음
#		- 주로 시계열 처리에 사용 (시계열:일정한 시간 간격의 데이터 열)
#		- RNN의 구조 중 하나
# 이전 계층을 사용하여 인코딩 된 행의 열을 인코딩합니다.
encoded_columns = LSTM(col_hidden)(encoded_rows)
# 이 두줄이 제일 노이해??????!!!!!!!!!!!!!!!!!????????????!!!!!!!!!!!
 
### set up prediction and compile the model  # 예측을 설정하고 모델을 컴파일하십시오.
prediction = Dense(num_classes, activation='softmax')(encoded_columns)
# Dense(유닛의 수, 활성화 함수의 종류) : 레이어 생성
# -> 활성화 함수로 softmax방법을 사용하는 유닛이 2개인 레이어 하나를 생성
# 유닛 : 결과일 수 있는 값들 / softmax : 확률을 통한 분류
model = Model(x, prediction)  # Dense 레이어를 모델에 추가(?)
# Model(input,output)
model.compile(loss='categorical_crossentropy', ### 카테고리 분류를 위한 손실함수 선택 - 확률 오차 계산
              optimizer='NAdam',               ### NAdam 최적화
              metrics=['accuracy'])            ### 정확도
# 학습알고리즘 - 학습 방식을 지정
# model.compile(loss=손실함수, optimizer=최적화 알고리즘, metrics=학습과정 중 보고 싶은 값 지정)


### 최상의 결과를 얻으려면 파일 경로를 만드십시오.
### http://machinelearningmastery.com/check-point-deep-learning-models-keras/
### 누가이 미친 물건을 두 번 이상 훈련시키고 싶어하니 ??!
i=0; filepath='HRNN_pretrained_model.hdf5'
# hdf5 (hdf ver.5) : 대용량 데이터를 저장하기 위한 파일 포맷  ex) 고성능DB 같은
#  - 많은 양의 데이터를 카테고리, 속성 별로 나눠 저장 가능 / numpy를 이용해 데이터에 접근 가능
checkpoint = ModelCheckpoint(filepath, monitor='val_acc', verbose=1, save_best_only=True, mode='max')
# ModelCheckpoint() : 정해놓은 경로에 모델을 저장
# verbose=1 : 학습이 진행되는 로그를 출력  ex) 학습진행률, 비용 등을 보여줌
callbacks_list = [checkpoint]
# callback : 모델이 epoch이 끝날 때마다 함수를 불러와 정해놓은 기능을 호출


### 이제 우리는 실제로 훈련을합니다.
### 왜냐하면 내 노트북 메모리 문제 때문에 파이썬이 충돌하기 때문에 훈련 데이터를 한 번에 메모리에로드 할 수 없다는 것을 의미합니다.
### 이 문제를 해결하기 위해 전체 데이터 세트를 로드하고 15개 배치로 반복합니다.
### 그러나 우리가 전체 데이터 세트를 통과 할 때마다 데이터의 순서를 무작위로 추출해야합니다.
### 그래서 각 epoch동안 파일 목록을 섞은 다음 15개의 비디오 묶음으로 나눕니다.
numpy.random.seed(18247)  ### 반복성을 위해 랜덤으로 시드를 설정한다.
# random.seed(값) : 동일한 순서로 난수를 발생시킴
# 파라미터 초기값을 랜덤하게 주더라도 일정하게 같은 값을 유지하도록 하기 위해서 사용

# ** x_train : 학습데이터 / y_train : 결과데이터  -> 쌍을 이루어 label을 구성
# ** label : 정답지
for i in range(0, 30):               ### epochs의 수
    c = list(zip(x_train, y_train))  ### 기능과 레이블을 함께 결합  # 학습데이터와 결과데이터를 합침 - label을 생성
    random.shuffle(c)                ### C리스트 변수(label)의 내용을 임의의 순서로(랜덤으로) 섞는다
    x_shuff, y_shuff = zip(*c)       ### unzip list into shuffled features and labels  # shuffled 기능 및 레이블에 목록 압축을 푼다.
    x_shuff = array(x_shuff); y_shuff=array(y_shuff) ### 배열로 변환
    
    x_batch = [x_shuff[i:i + batch_size] for i in range(0, len(x_shuff), batch_size)] ### make features into batches of 15  # 15 개의 배치로 기능 만들기
    y_batch = [y_shuff[i:i + batch_size] for i in range(0, len(x_shuff), batch_size)] ### make labels into batches of 15  # 15 개의 배치로 레이블 만들기
	# x_shuff[i+15]
	# for문 : 0부터 x_shuff의 길이까지 batch_size(15)단위로  -> i=0,15,30...
	# [i:i] : i부터 i까지

    for j,xb in enumerate(x_batch):  ### for each batch in the shuffled list for this epoch
		# enumerate(열거하다) : 인덱스 값과 값을 같이 반환 
        xx = make_dataset(xb)        ### load the feature data into arrays  # 기능데이터를 배열로 로드
        yy = y_batch[j]              ### set the labels for the batch  # 배치의 라벨을 설정
        
		# 학습
        model.fit(xx, yy,                            ### fit training data  # 맞춤 훈련 데이터
                  batch_size=len(xx),                ### reiterate batch size - in this case we already set up the batches  # 배치 크기를 반복 (이 경우 이미 배치를 설정함)
                  epochs=1,                          ### number of times to run through each batch  # 각 배치를 실행할 횟수
                  validation_data=(x_test, y_test),  ### validation set from up earlier in notebook  # 유효성 검사
                  callbacks=callbacks_list)          ### save if better than previous!  # 이전보다 좋으면 저장
	# 파이썬** len() : 길이를 반환 / zip() : 동일한 개수로 이루어진 자료형을 묶음
	# -> 완료시 모델에 학습된 결과물을 저장 - 모델에 처리할 연산들이 채워져 있는 상태

# 평가 - 테스트자료를 가지고 모델평가
scores = model.evaluate(x_test, y_test, verbose=0)    ### score model
print('Test loss:', scores[0])                        ### test loss
print('Test accuracy:', scores[1])                    ### test accuracy (ROC later)  # 시험 정확도


#### 결과 확인 - ROC 곡선

### 먼저, 저장된 모델을 로드하고 컴파일하여 예측을 하십시오.
model.load_weights("HRNN_pretrained_model.hdf5")  # 모델로드 - 학습을 다시 하지 않아도 됨
model.compile(loss='binary_crossentropy', optimizer='Nadam', metrics=['accuracy'])  # 모델 학습 방식 설정

### make the holdout test dataset for prediction and comparison
# 예측과 비교를위한 홀드 아웃 테스트 데이터 세트 만들기
x_holdout = make_dataset(x_testA)



plot([0,1],[0,1],'k:',alpha=0.5)                       ### plot the "by chance" line - the goal is to achieve better than random accuracy
ys = [y_train, y_test, y_testA]                        ### set up labels to be iterated through  # 반복되는 라벨 설정
labs = ['Train', 'Valid', 'Test']                      ### set up tags to be iterated through  # 반복되는 태그 설정
col = ['#4881ea', 'darkgreen', 'maroon']               ### set up colors to be iterated through  # 반복되는 색 설정
preds = []                                             ### set up prediction as empty array to populate  # 예측 저장할 배열
for i,xset in enumerate([x_train, x_testB, x_testA]):  ### 인덱스값(i)과 값(xset)을 같이 반환
    if i==0:  # for문 처음 한번
        new_pred = []                                  ### for first dataset, need to iterate through each  # 첫 번째 데이터 집합의 경우 각각을 반복해야합니다.
        for k in xset:                                 ### 메모리 절약 (한 번에 모든 것을로드 할 수 없기 때문)
            d = make_dataset([k])                
            new_pred.append(model.predict(d))          ### predictions with loaded model for each in training set  # 트레이닝 세트의 각 모델에 대한 로드 된 모델을 사용한 예측
        new_pred = array(new_pred).reshape((len(new_pred),2))
    else:
        d = make_dataset(xset)                         ### can load all of valid/test datasets at once in memory  # 모든 유효한 / 테스트 데이터 세트를 메모리에 한 번에로드 할 수 있습니다.
        new_pred = model.predict(d)                    ### predictions with loaded model for each valid/test dataset  # 각 유효 / 테스트 데이터 세트에 대해로드 된 모델로 예측
    preds.append(new_pred)
    # append() : 맨뒤에 요소 추가
	# predict(데이터) : 데이터를 가지고 모델이 학습한대로 연산,처리를 하고 결과를 리턴
	fpr, tpr, threshs = sklearn.metrics.roc_curve(ys[i][:,1], new_pred[:,1]) ### get the false pos rate and true pos rate
    plot(fpr, tpr, '-', color=col[i], alpha=0.7, lw=1.5, label=labs[i])      ### plot the ROC curve with false pos rate and true pos rate  # ROC곡선 그리기


    print labs[i]
    print sklearn.metrics.auc(fpr, tpr)                ### print area under curve for each set
    print sklearn.metrics.accuracy_score(ys[i][:,1], [round(j) for j in new_pred[:,1]])   ### print accuracy for each set
    print sklearn.metrics.confusion_matrix(ys[i][:,1], [round(j) for j in new_pred[:,1]]) ### print confusion matrix for each
    
xlabel('False Positive Rate'); ylabel('True Positive Rate')
plt.legend(fancybox=True, loc=4, prop={'size':10})  # 범례 - legend(loc=위치)
plt.show()



#### Examine probability range of predictions
# 예상 확률 범위 확인

plot([0,1],[0,1],'k:',alpha=0.5)                  ### plot the "by chance" line - trying so hard to be better than this...
for i,p in enumerate(preds):                      ### for each of the calculated predictions, make a histogram
    hist(p[:,1], bins = arange(0,1,0.05), histtype='stepfilled', color=col[i], alpha=0.7, label=labs[i]
	# 괄호!!!! 닫기???????????!!!!!!!!!!!!!!!!?????????
xlabel('False Positive Rate'); ylabel('True Positive Rate')
plt.legend(fancybox=True, loc=2, prop={'size':10})
plt.show()  # 그래프를 보여줌