# backend/algorithms.py
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from config import TRAIN_N_JOBS

def build_custom_pipeline(config: dict, params: dict = None):
    """根据前端传来的配置，动态组装 Pipeline"""
    if not config:
        return None
    if params is None:
        params = {}
        
    steps = []
    
    # 1. 预处理积木
    preprocessor = config.get('preprocessor', 'none')
    if preprocessor == 'standard':
        steps.append(('scaler', StandardScaler()))
    elif preprocessor == 'minmax':
        steps.append(('scaler', MinMaxScaler()))
        
    # 2. 降维积木
    reducer = config.get('reducer', 'none')
    if reducer == 'pca':
        steps.append(('pca', PCA(n_components=0.95)))
        
    # 3. 算法积木（读取前端传来的参数）
    algorithm = config.get('algorithm', 'randomforest')
    
    if algorithm == 'randomforest':
        n_est = int(params.get('n_estimators', 100))
        steps.append(('clf', RandomForestClassifier(n_estimators=n_est, n_jobs=TRAIN_N_JOBS)))
        
    elif algorithm == 'svm':
        c_val = float(params.get('svm_C', 1.0))
        kernel_type = params.get('svm_kernel', 'rbf')
        steps.append(('clf', SVC(C=c_val, kernel=kernel_type, probability=True)))
        
    elif algorithm == 'logistic':
        lr_c = float(params.get('lr_C', 1.0))
        steps.append(('clf', LogisticRegression(C=lr_c, max_iter=1000)))
    else:
        raise ValueError(f"不支持的算法类型: {algorithm}")
        
    return Pipeline(steps)
