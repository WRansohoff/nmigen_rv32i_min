// Standard library includes.
#include <stdint.h>
#include <string.h>
// Device header files
#include "encoding.h"
#include "tubul.h"

// Pre-boot reset handler: disable interrupts, set the
// stack pointer, then call the 'main' method.
__attribute__( ( naked ) ) void reset_handler( void ) {
  // Disable interrupts.
  clear_csr( mstatus, MSTATUS_MIE );
  // Set the stack pointer.
  __asm__( "la sp, _sp" );
  // Call main(0, 0) in case 'argc' and 'argv' are present.
  __asm__( "li a0, 0\n\t"
           "li a1, 0\n\t"
           "call main" );
}

// Pre-defined memory locations for program initialization.
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss;
// 'main' method which gets called from the boot code.
int main( void ) {
  // Copy initialized data from .sidata (Flash) to .data (RAM)
  memcpy( &_sdata, &_sidata, ( ( void* )&_edata - ( void* )&_sdata ) );
  // Clear the .bss RAM section.
  memset( &_sbss, 0x00, ( ( void* )&_ebss - ( void* )&_sbss ) );

  // Connect GPIO pin 2 to the "neopixel" peripheral.
  IOMUX->CFG1 |= ( IOMUX_NPX1 << IOMUX2_O );
  // Set initial color values for 4 LEDs.
  #define NUM_LEDS ( 24 )
  volatile uint8_t color_bytes[ ( NUM_LEDS * 3 ) ];
  int cval = 0x07;
  for ( int i = 0; i < ( NUM_LEDS * 3 ); ++i ) {
    color_bytes[ i ] = cval;
    ++cval;
  }
  // Set the colors address and length in the peripehral.
  NPX1->ADR = ( uint32_t )&color_bytes;
  NPX1->CR |= ( NUM_LEDS << NPX_CR_LEN_O );
  int progress = 0;
  while( 1 ) {
    // Send color values in a loop.
    while( ( NPX1->CR & NPX_CR_BSY_M ) != 0 ) {};
    NPX1->CR |= NPX_CR_BSY_M;
    // Set new color values.
    ++progress;
    for ( int i = 0; i < ( NUM_LEDS * 3 ); i += 3 ) {
      color_bytes[ i ] = ( progress >> 0 ) & 0xFF;
      color_bytes[ i + 1 ] = ( progress >> 2 ) & 0xFF;
      color_bytes[ i + 2 ] = ( progress >> 4 ) & 0xFF;
    }
  }
  return 0; // lol
}
