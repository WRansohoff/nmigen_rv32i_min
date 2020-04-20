// Standard library includes.
#include <stdint.h>
#include <string.h>
// Device header files
#include "encoding.h"
#include "tubul.h"

// 'step' exponent for the rainbow wheel algorithm
#define NUM_LEDS ( 24 )
#define SSFT  ( 5 )
#define STEP  ( 1 << SSFT )
#define SMAX  ( STEP * 6 )
#define ISTEP ( SMAX / NUM_LEDS )
// Storage for LED colors.
volatile uint8_t color_bytes[ ( NUM_LEDS * 3 ) ];

// Set an LED to a rainbow color based on a 'progress' count.
// There are no multiply or divide hardware instructions, so 'STEP'
// needs to be a constant and a power of two to avoid inefficient
// software math routines. Also, "x * 0xFF" = "( x << 8 ) - x"
void led_rainbow( int ind, int prg ) {
  // Red color.
  if ( ( ( prg > 0 ) && ( prg < STEP ) ) || ( prg > ( STEP * 5 ) ) ) {
    color_bytes[ ind + 1 ] = 0xFF;
  }
  else if ( ( prg > ( STEP * 2 ) ) && ( prg < ( STEP * 4 ) ) ) {
    color_bytes[ ind + 1 ] = 0x00;
  }
  else if ( prg < ( STEP * 2 ) ) {
    color_bytes[ ind + 1 ] = 0xFF - ( ( ( ( prg - STEP ) << 8 ) - ( prg - STEP ) ) >> SSFT );
  }
  else {
    color_bytes[ ind + 1 ] = ( ( ( prg - ( STEP * 4 ) ) << 8 ) - ( prg - ( STEP * 4 ) ) ) >> SSFT;
  }
  // Green color.
  if ( ( ( prg > STEP ) && ( prg < ( STEP * 3 ) ) ) ) {
    color_bytes[ ind ] = 0xFF;
  }
  else if ( ( prg >= ( STEP * 4 ) ) ) {
    color_bytes[ ind ] = 0x00;
  }
  else if ( ( prg > ( STEP * 3 ) ) && ( prg < ( STEP * 4 ) ) ) {
    color_bytes[ ind ] = 0xFF - ( ( ( ( prg - ( STEP * 3 ) ) << 8 ) - ( prg - ( STEP * 3 ) ) ) >> SSFT );
  }
  else {
    color_bytes[ ind ] = ( ( prg << 8 ) - prg ) >> SSFT;
  }
  // Blue color.
  if ( ( prg > ( STEP * 3 ) ) && ( prg < ( STEP * 5 ) ) ) {
    color_bytes[ ind + 2 ] = 0xFF;
  }
  else if ( ( prg < ( STEP * 2 ) ) ) {
    color_bytes[ ind + 2 ] = 0x00;
  }
  else if ( ( prg > ( STEP * 5 ) ) ) {
    color_bytes[ ind + 2 ] = 0xFF - ( ( ( ( prg - ( STEP * 5 ) ) << 8 ) - ( prg - ( STEP * 5 ) ) ) >> SSFT );
  }
  else {
    color_bytes[ ind + 2 ] = ( ( ( prg - ( STEP * 2 ) ) << 8 ) - ( prg - ( STEP * 2 ) ) ) >> SSFT;
  }
}

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

  // Connect GPIO pins 2 and 46 to the "neopixel" peripherals.
  IOMUX->CFG1 |= ( IOMUX_NPX1 << IOMUX2_O );
  IOMUX->CFG6 |= ( IOMUX_NPX2 << IOMUX46_O );
  // Set the colors address and length in the peripehrals.
  NPX1->ADR = ( uint32_t )&color_bytes;
  NPX1->CR |= ( NUM_LEDS << NPX_CR_LEN_O );
  // Use the same 'colors' array with the second peripheral, but
  // with an offset and half as many LEDs. That should test that the
  // bus arbiter timeshares RAM access correctly, since it will
  // handle both non-contiguous and shared memory access between
  // loads/stores and both of the 'neopixel' peripherals.
  NPX2->ADR = ( uint32_t )&color_bytes[ NUM_LEDS / 2 ];
  NPX2->CR |= ( ( NUM_LEDS / 2 ) << NPX_CR_LEN_O );

  // Progress counters.
  int progress = 0;
  int iprg = 0;

  // Main loop.
  while( 1 ) {
    // Set new color values.
    for ( int i = 0; i < ( NUM_LEDS * 3 ); i += 3 ) {
      led_rainbow( i, iprg );
      iprg += ISTEP;
      if ( iprg > SMAX ) { iprg -= SMAX; }
    }
    ++progress;
    if ( progress > SMAX ) { progress -= SMAX; }
    iprg = progress;

    // Start async transfer once the current one finishes.
    // TODO: 'transfer complete' would be a good candidate for an
    // interrupt, once I can fit software interrupts in the design...
    while( ( NPX1->CR & NPX_CR_BSY_M ) != 0 ) {};
    NPX1->CR |= NPX_CR_BSY_M;
    while( ( NPX2->CR & NPX_CR_BSY_M ) != 0 ) {};
    NPX2->CR |= NPX_CR_BSY_M;
  }
  return 0; // lol
}
