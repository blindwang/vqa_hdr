/* The copyright in this software is being made available under the BSD
 * License, included below. This software may be subject to other third party
 * and contributor rights, including patent rights, and no such rights are
 * granted under this license.
 *
 * <OWNER> = Apple Inc.
 * <ORGANIZATION> = Apple Inc.
 * <YEAR> = 2014
 *
 * Copyright (c) 2014, Apple Inc.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 *  * Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *  * Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *  * Neither the name of the <ORGANIZATION> nor the names of its contributors may
 *    be used to endorse or promote products derived from this software without
 *    specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
 * BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
 * THE POSSIBILITY OF SUCH DAMAGE.
 */

/*!
 *************************************************************************************
 * \file InputJPEG.cpp
 *
 * \brief
 *    InputJPEG class C++ file for allowing input from PNG files
 * 
 *    libpng manual: http://www.libpng.org/pub/png/libpng-manual.txt
 *
 * \author
 *     - Dimitri Podborski
 *
 *************************************************************************************
 */

//-----------------------------------------------------------------------------
// Include headers
//-----------------------------------------------------------------------------
#ifdef LIBJPEG
#include <vector>
#include <string.h>
#include <assert.h>
#include "InputJPEG.H"
#include "Global.H"
#include "IOFunctions.H"

#include <jpeglib.h>

//-----------------------------------------------------------------------------
// Macros/Defines
//-----------------------------------------------------------------------------
//#define __PRINT_INPUT_PNG__

namespace hdrtoolslib {

//-----------------------------------------------------------------------------
// Constructor/destructor
//-----------------------------------------------------------------------------

InputJPEG::InputJPEG(IOVideo *videoFile, FrameFormat *format) {
  m_isFloat         = FALSE;
  format->m_isFloat = m_isFloat;
  videoFile->m_format.m_isFloat = m_isFloat;
  m_frameRate = format->m_frameRate;
  auto PQ           = getFraction(m_frameRate);
  m_frameRateNum    = PQ.first;
  m_frameRateDenom  = PQ.second;

  m_size      = 0;  
  m_buf       = NULL;

  m_floatComp[Y_COMP] = NULL;
  m_floatComp[U_COMP] = NULL;
  m_floatComp[V_COMP] = NULL;
  m_floatComp[A_COMP] = NULL;
  
  m_ui16Comp[Y_COMP] = NULL;
  m_ui16Comp[U_COMP] = NULL;
  m_ui16Comp[V_COMP] = NULL;
  m_ui16Comp[A_COMP] = NULL;
  
  m_colorPrimaries   = format->m_colorPrimaries;
  m_sampleRange      = format->m_sampleRange;
  m_transferFunction = format->m_transferFunction;
  m_systemGamma      = format->m_systemGamma;

}

InputJPEG::~InputJPEG() {
  m_comp[Y_COMP]     = NULL;
  m_comp[U_COMP]     = NULL;
  m_comp[V_COMP]     = NULL;
  m_comp[A_COMP]     = NULL;
  
  m_ui16Comp[Y_COMP] = NULL;
  m_ui16Comp[U_COMP] = NULL;
  m_ui16Comp[V_COMP] = NULL;
  m_ui16Comp[A_COMP] = NULL;
  
  m_floatComp[Y_COMP] = NULL;
  m_floatComp[U_COMP] = NULL;
  m_floatComp[V_COMP] = NULL;
  m_floatComp[A_COMP] = NULL;
  clear();
}


/*!
 ************************************************************************
 * \brief
 *    Open file containing a single frame
 ************************************************************************
 */
FILE* InputJPEG::openFrameFile( IOVideo *inputFile, int FrameNumberInFile)
{
  char inFile [FILE_NAME_SIZE], in_number[16];
  int length = 0;
  in_number[length]='\0';
  length = (int) strlen(inputFile->m_fHead);
  strncpy(inFile, inputFile->m_fHead, sizeof(inFile));
  inFile[length]='\0';
  
  // Is this a single frame file? If yes, m_fTail would be of size 0.
  if (strlen(inputFile->m_fTail) != 0) {
    if (inputFile->m_zeroPad == TRUE)
      snprintf(in_number, 16, "%0*d", inputFile->m_numDigits, FrameNumberInFile);
    else
      snprintf(in_number, 16, "%*d", inputFile->m_numDigits, FrameNumberInFile);
    
    //strncat(inFile, in_number, sizeof(in_number));
    strncat(inFile, in_number, FILE_NAME_SIZE - strlen(inFile) - 1);
    length += sizeof(in_number);
    inFile[length]='\0';
    strncat(inFile, inputFile->m_fTail, FILE_NAME_SIZE - strlen(inFile) - 1);
    length += (int) strlen(inputFile->m_fTail);
    inFile[length]='\0';
  }

  FILE *fp = fopen(inFile, "rb");
  if(fp == NULL) {
    printf("InputJPEG::openFrameFile: cannot open file %s\n", inFile);
  }
  return fp;
}

int InputJPEG::readJPEG(FrameFormat *format, FILE *fp)
{
  // based on https://github.com/libjpeg-turbo/libjpeg-turbo/blob/main/example.txt
  struct jpeg_decompress_struct cinfo;
  struct jpeg_error_mgr jerr;
  JSAMPARRAY buffer;            /* Output row buffer */
  int row_stride;               /* physical row width in output buffer */

  /* Step 1: allocate and initialize JPEG decompression object */
  cinfo.err = jpeg_std_error(&jerr);
  jpeg_create_decompress(&cinfo);

  /* Step 2: specify a file data source */
  jpeg_stdio_src(&cinfo, fp);

  /* Step 3: read file parameters with jpeg_read_header() */
  (void) jpeg_read_header(&cinfo, TRUE);

  /* Step 4: Skip setting parameters for decompression, use defaults */

  /* Step 5: Start decompressor */
  (void) jpeg_start_decompress(&cinfo);

  int width = cinfo.output_width;
  int height = cinfo.output_height;
  int bitDepth = cinfo.data_precision;

  if(cinfo.out_color_components != cinfo.output_components)
  {
    printf("components mismatch %i vs %i.\n", cinfo.out_color_components, cinfo.output_components);
    (void) jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    return 1;
  }

  m_isInterleaved = FALSE;
  format->m_isInterlaced = m_isInterlaced = FALSE;

  switch(cinfo.out_color_space)
  {
  case JCS_RGB:
  case JCS_EXT_RGB: 
  case JCS_EXT_BGR:
    format->m_colorSpace = m_colorSpace = CM_RGB;
    format->m_chromaFormat = m_chromaFormat = CF_444;
    format->m_pixelFormat = m_pixelFormat = PF_RGB;
    if(cinfo.out_color_space == JCS_EXT_BGR) {
      format->m_pixelFormat = m_pixelFormat = PF_BGR;
    }
    break;
  case JCS_GRAYSCALE:
    format->m_colorSpace = m_colorSpace = CM_UNKNOWN;
    format->m_chromaFormat = m_chromaFormat = CF_400;
    format->m_pixelFormat = m_pixelFormat = PF_UNKNOWN;
    break;
  // case JCS_YCbCr:
  //   format->m_colorSpace = m_colorSpace = CM_YCbCr;
  //   format->m_chromaFormat = m_chromaFormat = CF_444;
  //   format->m_pixelFormat = m_pixelFormat = PF_UNKNOWN;
  //   break;
  default:
    printf("colorType %i is not supported.\n", cinfo.out_color_space);
    (void) jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    return 1;
  }
  
  m_width[Y_COMP]  = format->m_width[Y_COMP] = width;
  m_height[Y_COMP] = format->m_height[Y_COMP] = height;
  if(format->m_chromaFormat == CF_400) {
    m_width[U_COMP]  = m_width[V_COMP]  = format->m_width[U_COMP]  = format->m_width[V_COMP]  = 0;
    m_height[U_COMP] = m_height[V_COMP] = format->m_height[U_COMP] = format->m_height[V_COMP] = 0;
  }
  else if(format->m_chromaFormat == CF_444) {
    m_width[U_COMP]  = m_width[V_COMP]  = format->m_width[U_COMP]  = format->m_width[V_COMP]  = width;
    m_height[U_COMP] = m_height[V_COMP] = format->m_height[U_COMP] = format->m_height[V_COMP] = height;
  }
  else {
    printf("Chroma format not supported!\n");
    (void) jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    return 1;
  }

  format->m_compSize[Y_COMP] = m_compSize[Y_COMP] = m_height[Y_COMP] * m_width[Y_COMP];
  format->m_compSize[U_COMP] = m_compSize[U_COMP] = m_height[U_COMP] * m_width[U_COMP];
  format->m_compSize[V_COMP] = m_compSize[V_COMP] = m_height[V_COMP] * m_width[V_COMP];

  m_width[A_COMP]  = 0;
  m_height[A_COMP] = 0;
  format->m_width [A_COMP] = m_width[A_COMP];
  format->m_height[A_COMP] = m_height[A_COMP];
  format->m_compSize[A_COMP] = m_compSize[A_COMP] = m_height[A_COMP] * m_width[A_COMP];

  // Note that we do not read alpha but discard it
  format->m_size = m_size = m_compSize[Y_COMP] + m_compSize[U_COMP] + m_compSize[V_COMP] + m_compSize[A_COMP];
  
  format->m_bitDepthComp[Y_COMP] = m_bitDepthComp[Y_COMP] = bitDepth;
  format->m_bitDepthComp[U_COMP] = m_bitDepthComp[U_COMP] = bitDepth;
  format->m_bitDepthComp[V_COMP] = m_bitDepthComp[V_COMP] = bitDepth;
  format->m_bitDepthComp[A_COMP] = m_bitDepthComp[A_COMP] = bitDepth;

  m_chromaLocation[FP_TOP]    = format->m_chromaLocation[FP_TOP];
  m_chromaLocation[FP_BOTTOM] = format->m_chromaLocation[FP_BOTTOM];
  
  if (m_isInterlaced == FALSE && m_chromaLocation[FP_TOP] != m_chromaLocation[FP_BOTTOM]) {
    printf("Progressive Content. Chroma Type Location needs to be the same for both fields.\n");
    printf("Resetting Bottom field chroma location from type %d to type %d\n", m_chromaLocation[FP_BOTTOM], m_chromaLocation[FP_TOP]);
    m_chromaLocation[FP_BOTTOM] = format->m_chromaLocation[FP_BOTTOM] = m_chromaLocation[FP_TOP];    
  }

  // set the component pointers
  m_ui16Comp[Y_COMP] =m_ui16Comp[U_COMP] = m_ui16Comp[V_COMP] = m_ui16Comp[A_COMP] = NULL;
  m_comp[Y_COMP] = m_comp[U_COMP] = m_comp[V_COMP] = m_comp[A_COMP] = NULL;
  m_floatComp[Y_COMP] = m_floatComp[U_COMP] = m_floatComp[V_COMP] = m_floatComp[A_COMP] = NULL;
  if(m_bitDepthComp[Y_COMP] == 8) {
    m_data.resize((unsigned int) m_size);
    m_comp[Y_COMP]      = &m_data[0];
    if(format->m_chromaFormat == CF_444) {
      m_comp[U_COMP]      = m_comp[Y_COMP] + m_compSize[Y_COMP];
      m_comp[V_COMP]      = m_comp[U_COMP] + m_compSize[U_COMP];
    }
  } 
  else if (m_bitDepthComp[Y_COMP] == 16) {
    m_ui16Data.resize((unsigned int) m_size);
    m_ui16Comp[Y_COMP]  = &m_ui16Data[0];
    if(format->m_chromaFormat == CF_444) {
      m_ui16Comp[U_COMP]  = m_ui16Comp[Y_COMP] + m_compSize[Y_COMP];
      m_ui16Comp[V_COMP]  = m_ui16Comp[U_COMP] + m_compSize[U_COMP];
    }
  }
  else {
    printf("Bitdepth %i is not supported\n", m_bitDepthComp[Y_COMP]);
    (void) jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    return 1;
  }

  /* Step 6: read data */

  row_stride = width * cinfo.output_components;
  buffer = (*cinfo.mem->alloc_sarray)((j_common_ptr) &cinfo, JPOOL_IMAGE, row_stride, 1);

  while (cinfo.output_scanline < cinfo.output_height)
  {
    int i = cinfo.output_scanline;
    (void) jpeg_read_scanlines(&cinfo, buffer, 1);
    for (int j = 0; j < width; j++) 
    {
      m_comp[Y_COMP][i * m_width[Y_COMP] + j] = buffer[0][cinfo.output_components * j];
      m_comp[U_COMP][i * m_width[U_COMP] + j] = buffer[0][cinfo.output_components * j + 1];
      m_comp[V_COMP][i * m_width[V_COMP] + j] = buffer[0][cinfo.output_components * j + 2];
    }
  }

  // uint32 N = row_bytes / width;
  // if(bitDepth == 8) 
  // {
  //   for(int i=0; i<m_height[Y_COMP]; i++) {
  //     for(int j=0; j<m_width[Y_COMP]; j++) {
  //       if(format->m_chromaFormat == CF_444) {
  //         m_comp[Y_COMP][i * m_width[Y_COMP] + j] = row_pointers[i][j*N + 0];
  //         m_comp[U_COMP][i * m_width[U_COMP] + j] = row_pointers[i][j*N + 1];
  //         m_comp[V_COMP][i * m_width[V_COMP] + j] = row_pointers[i][j*N + 2];
  //       }
  //       else {
  //         m_comp[Y_COMP][i * m_width[Y_COMP] + j] = row_pointers[i][j];
  //       }
  //     }
  //   }
  // }
  // else if(bitDepth == 16) 
  // {
  //   for(int i=0; i<m_height[Y_COMP]; i++) {
  //     for(int j=0; j<m_width[Y_COMP]; j++) {
  //       if(format->m_chromaFormat == CF_444) {
  //         m_ui16Comp[Y_COMP][i * m_width[Y_COMP] + j] = (row_pointers[i][j*N + 0] << 8) + row_pointers[i][j*N + 1];
  //         m_ui16Comp[U_COMP][i * m_width[U_COMP] + j] = (row_pointers[i][j*N + 2] << 8) + row_pointers[i][j*N + 3];
  //         m_ui16Comp[V_COMP][i * m_width[V_COMP] + j] = (row_pointers[i][j*N + 4] << 8) + row_pointers[i][j*N + 5];
  //       }
  //       else {
  //         auto byte1 = row_pointers[i][j*2*2 + 0];
  //         auto byte2 = row_pointers[i][j*2*2 + 1];
  //         m_ui16Comp[Y_COMP][i * m_width[Y_COMP] + j] = (row_pointers[i][j*N + 0] << 8) + row_pointers[i][j*N + 1];
  //       }
  //     }
  //   }
  // }
  // else {
  //   printf("Bitdepth %i is currently not supported.\n", bitDepth);
  //   (void) jpeg_finish_decompress(&cinfo);
  //   jpeg_destroy_decompress(&cinfo);
  //   return -1;
  // }

  /* Step 7: Finish decompression */
  (void) jpeg_finish_decompress(&cinfo);
  /* Step 8: Release JPEG decompression object */
  jpeg_destroy_decompress(&cinfo);
  return 0;
}

void InputJPEG::printImage() const
{
  if(m_bitDepthComp[Y_COMP] == 8) {
    printf("m_comp[Y_COMP]\n");
    for(int i=0; i<m_height[Y_COMP]; i++) {
      for(int j=0; j<m_width[Y_COMP]; j++) {
        printf("%4i ", m_comp[Y_COMP][j+i*m_height[Y_COMP]]);
      }
      printf("\n");
    }
    printf("\n");
  }
  else if (m_bitDepthComp[Y_COMP] == 16) {
    printf("m_ui16Comp[Y_COMP]\n");
    for(int i=0; i<m_height[Y_COMP]; i++) {
      for(int j=0; j<m_width[Y_COMP]; j++) {
        printf("%4i ", m_ui16Comp[Y_COMP][j+i*m_height[Y_COMP]]);
      }
      printf("\n");
    }
    printf("\n");
  }
}

//-----------------------------------------------------------------------------
// Public methods
//-----------------------------------------------------------------------------

/*!
 ************************************************************************
 * \brief
 *    Reads one new frame from a single PNG file
 *
 * \param inputFile
 *    Input file to read from
 * \param frameNumber
 *    Frame number in the source file
 * \param fileHeader
 *    Number of bytes in the source file to be skipped
 * \param frameSkip
 *    Start position in file
 ************************************************************************
 */
int InputJPEG::readOneFrame (IOVideo *inputFile, int frameNumber, int fileHeader, int frameSkip) {
  FILE* fp = openFrameFile(inputFile, frameNumber + frameSkip);
  if(fp==NULL) {
    return 0;
  }

  int iRetVal = readJPEG(&inputFile->m_format, fp);

  fclose(fp);
  return iRetVal == 0;
}
} // namespace hdrtoolslib

#endif
//-----------------------------------------------------------------------------
// End of file
//-----------------------------------------------------------------------------

