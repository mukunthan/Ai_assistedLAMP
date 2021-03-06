import cv2
import numpy  as np
from skimage.feature import peak_local_max
from scipy.signal    import find_peaks

# from .NMS import NMS

# __all__ = ['NMS']
# __version__ = '1.5.3'

def _findLocalMax_(corrMap, score_threshold=0.6):
    '''
    Get coordinates of the local maximas with values above a threshold in the image of the correlation map
    '''
    
    # IF depending on the shape of the correlation map
    if corrMap.shape == (1,1): ## Template size = Image size -> Correlation map is a single digit')
        
        if corrMap[0,0]>=score_threshold:
            Peaks = np.array([[0,0]])
        else:
            Peaks = []

    # use scipy findpeaks for the 1D cases (would allow to specify the relative threshold for the score directly here rather than in the NMS
    elif corrMap.shape[0] == 1:     ## Template is as high as the image, the correlation map is a 1D-array
        Peaks = find_peaks(corrMap[0], height=score_threshold) # corrMap[0] to have a proper 1D-array
        Peaks = [[0,i] for i in Peaks[0]] # 0,i since one coordinate is fixed (the one for which Template = Image)
        

    elif corrMap.shape[1] == 1: ## Template is as wide as the image, the correlation map is a 1D-array
        #Peaks    = argrelmax(corrMap, mode="wrap")
        Peaks = find_peaks(corrMap[:,0], height=score_threshold)
        Peaks = [[i,0] for i in Peaks[0]]


    else: # Correlatin map is 2D
        Peaks = peak_local_max(corrMap, threshold_abs=score_threshold, exclude_border=False).tolist()

    return Peaks



def _findLocalMin_(corrMap, score_threshold=0.4):
    '''Find coordinates of local minimas with values below a threshold in the image of the correlation map'''
    return _findLocalMax_(-corrMap, -score_threshold)


def computeScoreMap(template, image, method=cv2.TM_CCOEFF_NORMED):
    '''
    Compute score map provided numpy array for template and image.
    Automatically converts images if necessary
    return score map as numpy as array
    '''
    if template.dtype == "float64" or image.dtype == "float64": 
        raise ValueError("64-bit not supported, max 32-bit")
        
    # Convert images if not both 8-bit (OpenCV matchTempalte is only defined for 8-bit OR 32-bit)
    if not (template.dtype == "uint8" and image.dtype == "uint8"):
        template = np.float32(template)
        image    = np.float32(image)
    
    # Compute correlation map
    return cv2.matchTemplate(template, image, method)


def findMatches(listTemplates, image, method=cv2.TM_CCOEFF_NORMED, N_object=float("inf"), score_threshold=0.5, searchBox=None):
    '''
    Find all possible templates locations provided a list of template to search and an image
    Parameters
    ----------
    - listTemplates : list of tuples (LabelString, Grayscale or RGB numpy array)
                    templates to search in each image, associated to a label 
    - image  : Grayscale or RGB numpy array
               image in which to perform the search, it should be the same bitDepth and number of channels than the templates
    - method : int 
                one of OpenCV template matching method (0 to 5), default 5=0-mean cross-correlation
    - N_object: int
                expected number of objects in the image
    - score_threshold: float in range [0,1]
                if N>1, returns local minima/maxima respectively below/above the score_threshold
    - searchBox : tuple (X, Y, Width, Height) in pixel unit
                optional rectangular search region as a tuple
    
    Returns
    -------
    - Pandas DataFrame with 1 row per hit and column "TemplateName"(string), "BBox":(X, Y, Width, Height), "Score":float 
    '''
    if N_object!=float("inf") and type(N_object)!=int:
        raise TypeError("N_object must be an integer")
        
    elif N_object<1:
        raise ValueError("At least one object should be expected in the image")
        
    ## Crop image to search region if provided
    if searchBox != None: 
        xOffset, yOffset, searchWidth, searchHeight = searchBox
        image = image[yOffset:yOffset+searchHeight, xOffset:xOffset+searchWidth]
    else:
        xOffset=yOffset=0
      
    listHit = []
    for templateName, template in listTemplates:
        
        #print('\nSearch with template : ',templateName)
        
        corrMap = computeScoreMap(template, image, method)

        ## Find possible location of the object 
        if N_object==1: # Detect global Min/Max
            minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(corrMap)
            
            if method==1:
                Peaks = [minLoc[::-1]] # opposite sorting than in the multiple detection
            
            elif method in (3,5):
                Peaks = [maxLoc[::-1]]
            
            
        else:# Detect local max or min
            if method==1: # Difference => look for local minima
                Peaks = _findLocalMin_(corrMap, score_threshold)
            
            elif method in (3,5):
                Peaks = _findLocalMax_(corrMap, score_threshold)
            
        
        #print('Initially found',len(Peaks),'hit with this template')
        
        
        # Once every peak was detected for this given template
        ## Create a dictionnary for each hit with {'TemplateName':, 'BBox': (x,y,Width, Height), 'Score':coeff}
        
        height, width = template.shape[0:2] # slicing make sure it works for RGB too
        
        for peak in Peaks :
            coeff  = corrMap[tuple(peak)]
            newHit = [(templateName),  [ int(peak[1])+xOffset, int(peak[0])+yOffset, width, height ] , (coeff)]

            # append to list of potential hit before Non maxima suppression
            listHit.append(newHit)
    
    return np.asarray(listHit) # All possible hits before Non-Maxima Supression
    

def matchTemplates(listTemplates, image, method=cv2.TM_CCOEFF_NORMED, N_object=float("inf"), score_threshold=0.5, maxOverlap=0.25, searchBox=None):
    '''
    Search each template in the image, and return the best N_object location which offer the best score and which do not overlap
    Parameters
    ----------
    - listTemplates : list of tuples (LabelString, Grayscale or RGB numpy array)
                    templates to search in each image, associated to a label 
    - image  : Grayscale or RGB numpy array
               image in which to perform the search, it should be the same bitDepth and number of channels than the templates
    - method : int 
                one of OpenCV template matching method (0 to 5), default 5=0-mean cross-correlation
    - N_object: int
                expected number of objects in the image
    - score_threshold: float in range [0,1]
                if N>1, returns local minima/maxima respectively below/above the score_threshold
    - maxOverlap: float in range [0,1]
                This is the maximal value for the ratio of the Intersection Over Union (IoU) area between a pair of bounding boxes.
                If the ratio is over the maxOverlap, the lower score bounding box is discarded.
    - searchBox : tuple (X, Y, Width, Height) in pixel unit
                optional rectangular search region as a tuple
    
    Returns
    -------
    Pandas DataFrame with 1 row per hit and column "TemplateName"(string), "BBox":(X, Y, Width, Height), "Score":float                 
        if N=1, return the best matches independently of the score_threshold
        if N<inf, returns up to N best matches that passed the score_threshold
        if N=inf, returns all matches that passed the score_threshold
    '''
    if maxOverlap<0 or maxOverlap>1:
        raise ValueError("Maximal overlap between bounding box is in range [0-1]")
        
    tableHit = findMatches(listTemplates, image, method, N_object, score_threshold, searchBox)
    
    if method == 1:       bestHits = NMS(tableHit, N_object=N_object, maxOverlap=maxOverlap, sortAscending=True)
    
    elif method in (3,5): bestHits = NMS(tableHit, N_object=N_object, maxOverlap=maxOverlap, sortAscending=False)
    
    return bestHits


def drawBoxesOnRGB(image, tableHit, boxThickness=2, boxColor=(255, 255, 00), showLabel=False, labelColor=(255, 255, 0), labelScale=0.5 ):
    '''
    Return a copy of the image with predicted template locations as bounding boxes overlaid on the image
    The name of the template can also be displayed on top of the bounding box with showLabel=True
    Parameters
    ----------
    - image  : image in which the search was performed
    - tableHit: list of hit as returned by matchTemplates or findMatches
    - boxThickness: int
                    thickness of bounding box contour in pixels
    - boxColor: (int, int, int)
                RGB color for the bounding box
    - showLabel: Boolean
                Display label of the bounding box (field TemplateName)
    - labelColor: (int, int, int)
                RGB color for the label
    
    Returns
    -------
    outImage: RGB image
            original image with predicted template locations depicted as bounding boxes  
    '''
    # Convert Grayscale to RGB to be able to see the color bboxes
    if image.ndim == 2: outImage = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB) # convert to RGB to be able to show detections as color box on grayscale image
    else:               outImage = image.copy()
        
    for row in tableHit:
        x,y,w,h = row
        cv2.rectangle(outImage, (x, y), (x+w, y+h), color=boxColor, thickness=boxThickness)
#         if showLabel: cv2.putText(outImage, text=row['TemplateName'], org=(x, y), fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=labelScale, color=labelColor, lineType=cv2.LINE_AA) 
    
    return outImage


def drawBoxesOnGray(image, tableHit, boxThickness=2, boxColor=255, showLabel=False, labelColor=255, labelScale=0.5):
    '''
    Same as drawBoxesOnRGB but with Graylevel.
    If a RGB image is provided, the output image will be a grayscale image
    Parameters
    ----------
    - image  : image in which the search was performed
    - tableHit: list of hit as returned by matchTemplates or findMatches
    - boxThickness: int
                thickness of bounding box contour in pixels
    - boxColor: int
                Gray level for the bounding box
    - showLabel: Boolean
                Display label of the bounding box (field TemplateName)
    - labelColor: int
                Gray level for the label
    
    Returns
    -------
    outImage: Single channel grayscale image
            original image with predicted template locations depicted as bounding boxes
    '''
    # Convert RGB to grayscale
    if image.ndim == 3: outImage = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) # convert to RGB to be able to show detections as color box on grayscale image
    else:               outImage = image.copy()
        
    for index, row in tableHit.iterrows():
        x,y,w,h = row['BBox']
        cv2.rectangle(outImage, (x, y), (x+w, y+h), color=boxColor, thickness=boxThickness)
        if showLabel: cv2.putText(outImage, text=row['TemplateName'], org=(x, y), fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=labelScale, color=labelColor, lineType=cv2.LINE_AA) 
    
    return outImage



def Point_in_Rectangle(Point, Rectangle):
    '''Return True if a point (x,y) is contained in a Rectangle(x, y, width, height)'''
    # unpack variables
    Px, Py = Point
    Rx, Ry, w, h = Rectangle

    return (Rx <= Px) and (Px <= Rx + w -1) and (Ry <= Py) and (Py <= Ry + h -1) # simply test if x_Point is in the range of x for the rectangle 


def computeIoU(BBox1,BBox2):
    '''
    Compute the IoU (Intersection over Union) between 2 rectangular bounding boxes defined by the top left (Xtop,Ytop) and bottom right (Xbot, Ybot) pixel coordinates
    Code adapted from https://www.pyimagesearch.com/2016/11/07/intersection-over-union-iou-for-object-detection/
    '''
    #print('BBox1 : ', BBox1)
    #print('BBox2 : ', BBox2)
    
    # Unpack input (python3 - tuple are no more supported as input in function definition - PEP3113 - Tuple can be used in as argument in a call but the function will not unpack it automatically)
    Xleft1, Ytop1, Width1, Height1 = BBox1
    Xleft2, Ytop2, Width2, Height2 = BBox2
    
    # Compute bottom coordinates
    Xright1 = Xleft1 + Width1  -1 # we remove -1 from the width since we start with 1 pixel already (the top one)
    Ybot1    = Ytop1     + Height1 -1 # idem for the height

    Xright2 = Xleft2 + Width2  -1
    Ybot2    = Ytop2     + Height2 -1

    # determine the (x, y)-coordinates of the top left and bottom right points of the intersection rectangle
    Xleft  = max(Xleft1, Xleft2)
    Ytop   = max(Ytop1, Ytop2)
    Xright = min(Xright1, Xright2)
    Ybot   = min(Ybot1, Ybot2)
    
    # Compute boolean for inclusion
    BBox1_in_BBox2 = Point_in_Rectangle((Xleft1, Ytop1), BBox2) and Point_in_Rectangle((Xleft1, Ybot1), BBox2) and Point_in_Rectangle((Xright1, Ytop1), BBox2) and Point_in_Rectangle((Xright1, Ybot1), BBox2)
    BBox2_in_BBox1 = Point_in_Rectangle((Xleft2, Ytop2), BBox1) and Point_in_Rectangle((Xleft2, Ybot2), BBox1) and Point_in_Rectangle((Xright2, Ytop2), BBox1) and Point_in_Rectangle((Xright2, Ybot2), BBox1) 
    
    # Check that for the intersection box, Xtop,Ytop is indeed on the top left of Xbot,Ybot
    if BBox1_in_BBox2 or BBox2_in_BBox1:
        #print('One BBox is included within the other')
        IoU = 1
    
    elif Xright<Xleft or Ybot<Ytop : # it means that there is no intersection (bbox is inverted)
        #print('No overlap')
        IoU = 0 
    
    else:
        # Compute area of the intersecting box
        Inter = (Xright - Xleft + 1) * (Ybot - Ytop + 1) # +1 since we are dealing with pixels. See a 1D example with 3 pixels for instance
        #print('Intersection area : ', Inter)

        # Compute area of the union as Sum of the 2 BBox area - Intersection
        Union = Width1 * Height1 + Width2 * Height2 - Inter
        #print('Union : ', Union)
        
        # Compute Intersection over union
        IoU = Inter/Union
    
    #print('IoU : ',IoU)
    return IoU



def NMS(tableHit, scoreThreshold=None, sortAscending=False, N_object=float("inf"), maxOverlap=0.5):
    '''
    Perform Non-Maxima supression : it compares the hits after maxima/minima detection, and removes the ones that are too close (too large overlap)
    This function works both with an optionnal threshold on the score, and number of detected bbox

    if a scoreThreshold is specified, we first discard any hit below/above the threshold (depending on sortDescending)
    if sortDescending = True, the hit with score below the treshold are discarded (ie when high score means better prediction ex : Correlation)
    if sortDescending = False, the hit with score above the threshold are discared (ie when low score means better prediction ex : Distance measure)

    Then the hit are ordered so that we have the best hits first.
    Then we iterate over the list of hits, taking one hit at a time and checking for overlap with the previous validated hit (the Final Hit list is directly iniitialised with the first best hit as there is no better hit with which to compare overlap)    
    
    This iteration is terminate once we have collected N best hit, or if there are no more hit left to test for overlap 
   
   INPUT
    - tableHit         : (Panda DataFrame) Each row is a hit, with columns "TemplateName"(String),"BBox"(x,y,width,height),"Score"(float)
                        
    - scoreThreshold : Float (or None), used to remove hit with too low prediction score. 
                       If sortDescending=True (ie we use a correlation measure so we want to keep large scores) the scores above that threshold are kept
                       While if we use sortDescending=False (we use a difference measure ie we want to keep low score), the scores below that threshold are kept
                       
    - N_object                 : number of best hit to return (by increasing score). Min=1, eventhough it does not really make sense to do NMS with only 1 hit
    - maxOverlap    : float between 0 and 1, the maximal overlap authorised between 2 bounding boxes, above this value, the bounding box of lower score is deleted
    - sortAscending : use True when low score means better prediction (Difference-based score), True otherwise (Correlation score)

    OUTPUT
    Panda DataFrame with best detection after NMS, it contains max N detection (but potentially less)
    '''
#     print("shape of tableHit: {}".format(tableHit.shape))
    # Apply threshold on prediction score
    if scoreThreshold==None :
        threshTable = tableHit.copy() # copy to avoid modifying the input list in place
    
    elif not sortAscending : # We keep rows above the threshold
        threshTable = tableHit[ tableHit[:,2]>=scoreThreshold ]
        

    elif sortAscending : # We keep hit below the threshold
        threshTable = tableHit[ tableHit[:,2]<=scoreThreshold ]    
        
    
    # Sort score to have best predictions first (ie lower score if difference-based, higher score if correlation-based)
    # important as we loop testing the best boxes against the other boxes)
    

    if sortAscending:
        threshTable = threshTable[threshTable[:,2].argsort()]
    elif not sortAscending:
        threshTable = threshTable[threshTable[:,2].argsort()[::-1]]

    
    # Split the inital pool into Final Hit that are kept and restTable that can be tested
    # Initialisation : 1st keep is kept for sure, restTable is the rest of the list
    outTable  = threshTable[0:1,1] # double square bracket to recover a DataFrame
    restTable = threshTable[1:len(threshTable),1]
    

    # Loop to compute overlap
    while (len(outTable))<N_object and len(restTable)>0: # second condition is restTable is not empty
        
       
        # pick the next best peak in the rest of peak
        testHit_dico = restTable[0:1] # dico
        test_bbox = testHit_dico[0]
     
        # Loop over hit in outTable to compute successively overlap with testHit    
        for hit_dico in outTable: 
            

            
            # Recover Bbox from hit
            bbox2 = hit_dico 

            # Compute the Intersection over Union between test_peak and current peak
            IoU = computeIoU(test_bbox, bbox2)
            
            # Initialise the boolean value to true before test of overlap
            ToAppend = True 
    
            if IoU>maxOverlap:
                ToAppend = False
               
                break # no need to test overlap with the other peaks
            
            else:
                
                # no overlap for this particular (test_peak,peak) pair, keep looping to test the other (test_peak,peak)
                continue
      
        
        # After testing against all peaks (for loop is over), append or not the peak to final
        if ToAppend:
            # Move the test_hit from restTable to outTable
           
            outTable= np.append(outTable,testHit_dico)
            restTable =np.delete(restTable, np.where(restTable == testHit_dico))

            
        else:

            restTable =np.delete(restTable, np.where(restTable == testHit_dico))
    
    return outTable

            
