

# cython: profile=False 
# copile with py3 compiler.py build_ext --inplace
#changed from https://github.com/pandas-dev/pandas/blob/c1068d9d242c22cb2199156f6fb82eb5759178ae/pandas/_libs/algos.pyx

cimport cython
from cython cimport Py_ssize_t

from libc.stdlib cimport malloc, free
from libc.string cimport memmove
from libc.math cimport fabs, sqrt

import numpy as np
cimport numpy as cnp
from numpy cimport (ndarray,
                    NPY_INT64, NPY_UINT64, NPY_INT32, NPY_INT16, NPY_INT8,
                    NPY_FLOAT32, NPY_FLOAT64,
                    NPY_OBJECT,
                    int8_t, int16_t, int32_t, int64_t, uint8_t, uint16_t,
                    uint32_t, uint64_t, float32_t, float64_t,
                    double_t)
cnp.import_array()




cdef float64_t FP_ERR = 1e-13

cdef double NaN = <double> np.NaN
cdef double nan = NaN



@cython.boundscheck(False)
@cython.wraparound(False)
def nancorr(ndarray[float32_t, ndim=2] mat):
    cdef:
        Py_ssize_t i, j, xi, yi, N, K
        bint minpv
        ndarray[float32_t, ndim=2] sumSq
        ndarray[float32_t, ndim=2] crossN
        ndarray[float32_t, ndim=2] sumLin
        ndarray[uint8_t, ndim=2] mask
        float32_t nobs = 0
        float32_t vx, vy, sumx, sumy, sumxx, sumyy, sumxy

    N, K = (<object> mat).shape

    sumSq = np.empty((K, K), dtype=np.float32)
    sumLin = np.empty((K, K), dtype=np.float32)
    crossN = np.empty((K, K), dtype=np.float32)

    mask = np.isfinite(mat).view(np.uint8)

    with nogil:
        for xi in range(K):
          for yi in range(xi + 1):
              nobs = sumxx = sumyy = sumxy = sumx = sumy = 0
              for i in range(N):
                  if mask[i, xi] and mask[i, yi]:
                      vx = mat[i, xi]
                      vy = mat[i, yi]
                      nobs += 1
                      sumx += vx
                      sumy += vy
                      sumxy += vx * vy
                      sumxx += vx * vx 
                      sumyy += vy * vy
    
              sumSq[xi, yi] = sumxx
              sumSq[yi, xi] = sumyy
              sumLin[xi, yi] = sumx
              sumLin[yi, xi] = sumy
              crossN[xi, yi] = sumxy
              crossN[yi, xi] = nobs
                  

    return sumLin, sumSq, crossN

@cython.boundscheck(False)
@cython.wraparound(False)
def corr(ndarray[float32_t, ndim=2] sumLin, ndarray[float32_t, ndim=2] sumSq, 
        ndarray[float32_t, ndim=2] crossN):
    cdef: 
        int32_t i, j, N, K
        float32_t val
        ndarray[float32_t, ndim=2] results

    N, K = (<object> sumLin).shape
    results = np.empty((K,K), dtype=np.float32)

    for i in range(0,K):
        for j in range(i+1):
            val = crossN[j,i] * crossN[i,j] -  sumLin[i,j] * sumLin[j,i]
            d1 = np.sqrt( crossN[j,i] * sumSq[i,j] - sumLin[i,j] * sumLin[i,j])
            d2 = np.sqrt( crossN[j,i] * sumSq[j,i] - sumLin[j,i] * sumLin[j,i])
            if d1 == 0 or d2 == 0:
              val = np.nan
            else: 
              val /= (d1 * d2)
            results[i,j] = results[j,i] = val
        results[i,i] = 0.0 # obv this is 1 but this way testing is easier
    return results

@cython.boundscheck(False)
@cython.wraparound(False)
def process_plink_row(row, geno):
    cdef:
        int32_t missing, num_het, num_homo_alt
        float32_t item
        ndarray[int32_t, ndim=1] counts
    counts = np.empty((3), dtype=np.int32)   
    missing = 0
    num_het = 0
    num_homo_alt = 0
    for i, item in enumerate(row):
        if item == 3: 
            missing += 1
            geno[i] = np.nan
            continue
        if item == 1:
            num_het += 1
        elif item == 2:
            num_homo_alt += 1
        geno[i] = item
    counts[0] = num_het
    counts[1] = num_homo_alt
    counts[2] = missing
    return(counts, geno)
            


cdef extern from "plink2_stats.cpp":
  cpdef double HweP(int32_t obs_hets, int32_t obs_hom1, int32_t ob_hom2, uint32_t midp)
  #cpdef double HweP(ndarray[int32_t, ndim=1] obs_hets, ndarray[int32_t, ndim=1] obs_hom1,
  #    ndarray[int32_t, ndim=1] ob_hom2, uint32_t midp):
def  hweP(ndarray[int32_t, ndim=2] obs, uint32_t midp):
    cdef: 
        int32_t het, hom1, hom2, i, k
        ndarray[float64_t, ndim=1] results
    
    k,_ = (<object> obs).shape
    results = np.empty((k), dtype=np.float64)
    i = 0
    for hom1, het, hom2 in obs:
      results[i] = HweP(het, hom1, hom2, midp)
      i += 1

    return results


