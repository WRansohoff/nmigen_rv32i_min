#ifndef __TUBUL_DEVICE
#define __TUBUL_DEVICE

#include <stdint.h>

// Device header file:
// Currently, there's only a simple GPIO peripheral.
// GPIO struct: 4 registers, 16 pins per register.
typedef struct
{
  volatile uint32_t P1;
  volatile uint32_t P2;
  volatile uint32_t P3;
  volatile uint32_t P4;
} GPIO_TypeDef;

// Peripheral address definitions
#define GPIO ( ( GPIO_TypeDef * ) 0x40000000 )

// GPIO pin address offsets.
// (not every pin is an I/O pin)
#define GPIO2_O  ( 4 )
#define GPIO3_O  ( 6 )
#define GPIO4_O  ( 8 )
#define GPIO9_O  ( 18 )
#define GPIO11_O ( 22 )
#define GPIO12_O ( 24 )
#define GPIO13_O ( 26 )
#define GPIO18_O ( 4 )
#define GPIO19_O ( 6 )
#define GPIO21_O ( 10 )
#define GPIO23_O ( 14 )
#define GPIO25_O ( 18 )
#define GPIO26_O ( 20 )
#define GPIO27_O ( 22 )
#define GPIO31_O ( 30 )
#define GPIO32_O ( 0 )
#define GPIO33_O ( 2 )
#define GPIO34_O ( 4 )
#define GPIO35_O ( 6 )
#define GPIO36_O ( 8 )
#define GPIO37_O ( 10 )
#define GPIO38_O ( 12 )
#define GPIO39_O ( 14 )
#define GPIO40_O ( 16 )
#define GPIO41_O ( 18 )
#define GPIO42_O ( 20 )
#define GPIO43_O ( 22 )
#define GPIO44_O ( 24 )
#define GPIO45_O ( 26 )
#define GPIO46_O ( 28 )
#define GPIO47_O ( 30 )
#define GPIO48_O ( 0 )

#endif
