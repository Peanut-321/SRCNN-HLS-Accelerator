#ifndef _SRCNN_H_
#define _SRCNN_H_

// Image dimensions supplied by the course Golden Reference harness.
#define W 255
#define H 255
#define UP 3

// SRCNN topology.
#define N0 1
#define N1 64
#define F1 9
#define N2 32
#define F2 1
#define N3 1
#define F3 5

typedef float ftmap_t;
typedef float param_t;

// End-to-end SRCNN inference.
void srcnn(ftmap_t input_ftmap[N0][H][W],
           param_t conv1_weights[N1][N0][F1][F1],
           param_t conv1_biases[N1],
           param_t conv2_weights[N2][N1][F2][F2],
           param_t conv2_biases[N2],
           param_t conv3_weights[N3][N2][F3][F3],
           param_t conv3_biases[N3],
           ftmap_t output_ftmap[N3][H][W]);

// First layer, exposed separately for the supplied Conv1 testbench.
void conv1(ftmap_t input_ftmap[N0][H][W],
           param_t conv1_weights[N1][N0][F1][F1],
           param_t conv1_biases[N1],
           ftmap_t output_ftmap[N1][H][W]);

#endif  // _SRCNN_H_
