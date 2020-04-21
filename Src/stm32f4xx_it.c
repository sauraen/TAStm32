/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    stm32f4xx_it.c
  * @brief   Interrupt Service Routines.
  ******************************************************************************
  *
  * COPYRIGHT(c) 2019 STMicroelectronics
  *
  * Redistribution and use in source and binary forms, with or without modification,
  * are permitted provided that the following conditions are met:
  *   1. Redistributions of source code must retain the above copyright notice,
  *      this list of conditions and the following disclaimer.
  *   2. Redistributions in binary form must reproduce the above copyright notice,
  *      this list of conditions and the following disclaimer in the documentation
  *      and/or other materials provided with the distribution.
  *   3. Neither the name of STMicroelectronics nor the names of its contributors
  *      may be used to endorse or promote products derived from this software
  *      without specific prior written permission.
  *
  * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
  * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
  * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
  * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
  * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
  * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
  * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
  * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
  * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
  * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "stm32f4xx_it.h"
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "n64.h"
#include "TASRun.h"
#include "usbd_cdc_if.h"
#include "serial_interface.h"
#include "z64_tc.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN TD */

/* USER CODE END TD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
const uint8_t P1_D0_HIGH_C = 3;
const uint8_t P1_D0_LOW_C = 19;
const uint8_t P1_D1_HIGH_C = 2;
const uint8_t P1_D1_LOW_C = 18;
const uint8_t P1_D2_HIGH_C = 4;
const uint8_t P1_D2_LOW_C = 20;
const uint8_t P2_D0_HIGH_C = 8;
const uint8_t P2_D0_LOW_C = 24;
const uint8_t P2_D1_HIGH_C = 7;
const uint8_t P2_D1_LOW_C = 23;
const uint8_t P2_D2_HIGH_C = 9;
const uint8_t P2_D2_LOW_C = 25;
const uint8_t SNES_RESET_HIGH_A = 9;
const uint8_t SNES_RESET_LOW_A = 25;

const uint8_t V1_D0_HIGH_B = 7;
const uint8_t V1_D0_LOW_B = 23;
const uint8_t V1_D1_HIGH_B = 6;
const uint8_t V1_D1_LOW_B = 22;
const uint8_t V1_LATCH_HIGH_B = 5;
const uint8_t V1_LATCH_LOW_B = 21;
const uint8_t V1_CLOCK_HIGH_B = 4;
const uint8_t V1_CLOCK_LOW_B = 20;

const uint8_t V2_D0_HIGH_C = 12;
const uint8_t V2_D0_LOW_C = 28;
const uint8_t V2_D1_HIGH_C = 11;
const uint8_t V2_D1_LOW_C = 27;
const uint8_t V2_LATCH_HIGH_C = 10;
const uint8_t V2_LATCH_LOW_C = 26;
const uint8_t V2_CLOCK_HIGH_A = 15;
const uint8_t V2_CLOCK_LOW_A = 31;

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */
#define WAIT_4_CYCLES asm("ADD     R1, R2, #0\nADD     R1, R2, #0\nADD     R1, R2, #0\nADD     R1, R2, #0")
/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN PV */
volatile uint64_t p1_d0_next = 0;
volatile uint64_t p1_d1_next = 0;
volatile uint64_t p1_d2_next = 0;
volatile uint64_t p2_d0_next = 0;
volatile uint64_t p2_d1_next = 0;
volatile uint64_t p2_d2_next = 0;

// leave enough room for SNES + overread
uint32_t P1_GPIOC_current[17];
volatile uint32_t P1_GPIOC_next[17];

uint32_t P2_GPIOC_current[17];
volatile uint32_t P2_GPIOC_next[17];

volatile uint32_t V1_GPIOB_current[16];
volatile uint32_t V1_GPIOB_next[16];

volatile uint32_t V2_GPIOC_current[16];
volatile uint32_t V2_GPIOC_next[16];

uint8_t p1_current_bit = 0;
uint8_t p2_current_bit = 0;

volatile uint8_t recentLatch = 0;
volatile uint8_t toggleNext = 0;
volatile uint8_t dpcmFix = 0;
volatile uint8_t clockFix = 0;

volatile uint8_t p1_clock_filtered = 0;
volatile uint8_t p2_clock_filtered = 0;

// latch train vars
uint16_t current_train_index = 0;
uint16_t current_train_latch_count = 0;
uint8_t between_trains = 1;
uint8_t trains_enabled = 0;

uint16_t* latch_trains = NULL;

Console c = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN PFP */
void my_wait_us_asm(int n);
uint8_t UART2_OutputFunction(uint8_t *buffer, uint16_t n);
HAL_StatusTypeDef Simple_Transmit(UART_HandleTypeDef *huart);
void GCN64CommandStart(uint8_t player);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/* External variables --------------------------------------------------------*/
extern PCD_HandleTypeDef hpcd_USB_OTG_FS;
extern TIM_HandleTypeDef htim3;
extern TIM_HandleTypeDef htim6;
extern TIM_HandleTypeDef htim7;
extern TIM_HandleTypeDef htim10;
extern UART_HandleTypeDef huart2;
/* USER CODE BEGIN EV */
extern volatile uint8_t request_pending;
extern volatile uint8_t bulk_mode;
/* USER CODE END EV */

/******************************************************************************/
/*           Cortex-M4 Processor Interruption and Exception Handlers          */ 
/******************************************************************************/
/**
  * @brief This function handles System tick timer.
  */
void SysTick_Handler(void)
{
  /* USER CODE BEGIN SysTick_IRQn 0 */

  /* USER CODE END SysTick_IRQn 0 */
  HAL_IncTick();
  /* USER CODE BEGIN SysTick_IRQn 1 */

  /* USER CODE END SysTick_IRQn 1 */
}

/******************************************************************************/
/* STM32F4xx Peripheral Interrupt Handlers                                    */
/* Add here the Interrupt Handlers for the used peripherals.                  */
/* For the available peripheral interrupt handler names,                      */
/* please refer to the startup file (startup_stm32f4xx.s).                    */
/******************************************************************************/

/**
  * @brief This function handles EXTI line 0 interrupt.
  */
void EXTI0_IRQHandler(void)
{
  /* USER CODE BEGIN EXTI0_IRQn 0 */
	// P1_CLOCK
	if(!p1_clock_filtered && p1_current_bit < 17) // sanity check... but 32 or more bits should never be read in a single latch!
	{
		if(clockFix)
		{
			my_wait_us_asm(2); // necessary to prevent switching too fast in DPCM fix mode
		}

		GPIOC->BSRR = (P1_GPIOC_current[p1_current_bit] & 0x00080008); // set d0
		GPIOC->BSRR = (P1_GPIOC_current[p1_current_bit] & 0x00040004); // set d1
		//TODO: Determine why setting these at the same time causes an interrupt to go to line 1 for some reason!!!!!
		//GPIOC->BSRR = (P1_GPIOC_current[p1_current_bit] & 0x000C000C); // set d0 and d1 at the same time

		ResetAndEnableP1ClockTimer();
		p1_current_bit++;
	}
  /* USER CODE END EXTI0_IRQn 0 */
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_0);
  /* USER CODE BEGIN EXTI0_IRQn 1 */

  /* USER CODE END EXTI0_IRQn 1 */
}

/**
  * @brief This function handles EXTI line 1 interrupt.
  */
void EXTI1_IRQHandler(void)
{
  /* USER CODE BEGIN EXTI1_IRQn 0 */

	// P1_LATCH
	int8_t regbit = 50, databit = -1; // random initial values
	TASRun *tasrun = TASRunGetByIndex(RUN_A);

	if(recentLatch == 0) // no recent latch
	{
		// quickly set first bit of data for the next frame
		//GPIOC->BSRR = P1_GPIOC_next[0] | P2_GPIOC_next[0] | V2_GPIOC_next[0];
		GPIOC->BSRR = (P1_GPIOC_next[0] & 0x00080008) | P2_GPIOC_next[0];
		GPIOC->BSRR = (P1_GPIOC_next[0] & 0x00040004);

		// copy the 2nd bit over too
		__disable_irq();
		P1_GPIOC_current[1] = P1_GPIOC_next[1];
		P2_GPIOC_current[1] = P2_GPIOC_next[1];
		p1_current_bit = p2_current_bit = 1; // set the next bit to be read
		__enable_irq();

		// copy the rest of the bits. do not copy the overread since it will never change
		memcpy((uint32_t*)&P1_GPIOC_current, (uint32_t*)&P1_GPIOC_next, 64);
		memcpy((uint32_t*)&P2_GPIOC_current, (uint32_t*)&P2_GPIOC_next, 64);

		// now prepare for the next frame!

		if(toggleNext == 1)
		{
			dpcmFix = 1 - dpcmFix;
		}
		else if(toggleNext == 2)
		{
			GPIOA->BSRR = (1 << SNES_RESET_HIGH_A);
			HAL_Delay(200);
			GPIOA->BSRR = (1 << SNES_RESET_LOW_A);
			HAL_Delay(200);
		}
		else if(toggleNext == 3)
		{
			GPIOA->BSRR = (1 << SNES_RESET_HIGH_A);
			HAL_Delay(1000);
			GPIOA->BSRR = (1 << SNES_RESET_LOW_A);
			HAL_Delay(1000);
		}

		if(dpcmFix)
		{
			recentLatch = 1; // repeat input on latch
			ResetAndEnable8msTimer(); // start timer and proceed as normal
		}

		static RunData (*dataptr)[MAX_CONTROLLERS][MAX_DATA_LANES];

		if(trains_enabled)
		{
			if(between_trains == 1) // at least one lag frame detected
			{
				// do what you gotta do
				// adjust the frame of the run accordingly
				int diff = latch_trains[current_train_index] - current_train_latch_count;

				if(diff == 1) // we are one latch short
				{
					GetNextFrame(tasrun); // burn a frame of data
					dataptr = GetNextFrame(tasrun); // use this frame instead
					serial_interface_output((uint8_t*)"UB", 2);
				}
				else if(diff == -1) // we had one extra latch
				{
					// do NOT get next frame (yet). hold back for one
					serial_interface_output((uint8_t*)"UA", 2);
				}
				else if(diff != 0) // large deviation
				{
					// AHHHH!!!!!! Give some sort of unrecoverable error?
					serial_interface_output((uint8_t*)"UF", 2);
				}
				else // normalcy
				{
					dataptr = GetNextFrame(tasrun);
					serial_interface_output((uint8_t*)"UC", 2);
				}

				current_train_index++; // we have begun the next train
				current_train_latch_count = 1; // reset the latch count
				between_trains = 0; // we are no longer between trains
			}
			else
			{
				current_train_latch_count++;
				dataptr = GetNextFrame(tasrun);
			}

			DisableTrainTimer(); // reset counters back to 0
			ResetAndEnableTrainTimer();
		}
		else
		{
			dataptr = GetNextFrame(tasrun);
		}

		toggleNext = TASRunIncrementFrameCount(tasrun);

		if(dataptr)
		{
			c = TASRunGetConsole(tasrun);

			databit = 0;
			if(c == CONSOLE_NES)
			{
				databit = 7; // number of bits of NES - 1

				memcpy((uint8_t*)&p1_d0_next, &dataptr[0][0][0], sizeof(NESControllerData));
				memcpy((uint8_t*)&p1_d1_next, &dataptr[0][0][1], sizeof(NESControllerData));
				memcpy((uint8_t*)&p1_d2_next, &dataptr[0][0][2], sizeof(NESControllerData));
				memcpy((uint8_t*)&p2_d0_next, &dataptr[0][1][0], sizeof(NESControllerData));
				memcpy((uint8_t*)&p2_d1_next, &dataptr[0][1][1], sizeof(NESControllerData));
				memcpy((uint8_t*)&p2_d2_next, &dataptr[0][1][2], sizeof(NESControllerData));
			}
			else
			{
				databit = 15; // number of bits of SNES - 1

				memcpy((uint16_t*)&p1_d0_next, &dataptr[0][0][0], sizeof(SNESControllerData));
				memcpy((uint16_t*)&p1_d1_next, &dataptr[0][0][1], sizeof(SNESControllerData));
				memcpy((uint16_t*)&p2_d0_next, &dataptr[0][1][0], sizeof(SNESControllerData));
				memcpy((uint16_t*)&p2_d1_next, &dataptr[0][1][1], sizeof(SNESControllerData));

				// fix endianness
				p1_d0_next = ((p1_d0_next >> 8) & 0xFF) | ((p1_d0_next << 8) & 0xFF00);
				p1_d1_next = ((p1_d1_next >> 8) & 0xFF) | ((p1_d1_next << 8) & 0xFF00);
				p1_d2_next = ((p1_d2_next >> 8) & 0xFF) | ((p1_d2_next << 8) & 0xFF00);
				p2_d0_next = ((p2_d0_next >> 8) & 0xFF) | ((p2_d0_next << 8) & 0xFF00);
				p2_d1_next = ((p2_d1_next >> 8) & 0xFF) | ((p2_d1_next << 8) & 0xFF00);
				p2_d2_next = ((p2_d2_next >> 8) & 0xFF) | ((p2_d2_next << 8) & 0xFF00);
			}


			regbit = 0;

			// fill the regular data
			while(databit >= 0)
			{
				P1_GPIOC_next[regbit] = (uint32_t)(((p1_d0_next >> databit) & 1) << P1_D0_LOW_C) |
										(uint32_t)(((p1_d1_next >> databit) & 1) << P1_D1_LOW_C) |
										(uint32_t)(((p1_d2_next >> databit) & 1) << P1_D2_LOW_C);
				P1_GPIOC_next[regbit] |= (((~P1_GPIOC_next[regbit]) & 0x001C0000) >> 16);

				P2_GPIOC_next[regbit] = (uint32_t)(((p2_d0_next >> databit) & 1) << P2_D0_LOW_C) |
										(uint32_t)(((p2_d1_next >> databit) & 1) << P2_D1_LOW_C) |
										(uint32_t)(((p2_d2_next >> databit) & 1) << P2_D2_LOW_C);
				P2_GPIOC_next[regbit] |= (((~P2_GPIOC_next[regbit]) & 0x03800000) >> 16);

				V1_GPIOB_next[regbit] = (uint32_t)(((p1_d0_next >> databit) & 1) << V1_D0_HIGH_B) |
										(uint32_t)(((p1_d1_next >> databit) & 1) << V1_D1_HIGH_B);
				V1_GPIOB_next[regbit] |= (((~V1_GPIOB_next[regbit]) & 0x00C0) << 16);

				V2_GPIOC_next[regbit] = (uint32_t)(((p2_d0_next >> databit) & 1) << V2_D0_HIGH_C) |
										(uint32_t)(((p2_d1_next >> databit) & 1) << V2_D1_HIGH_C);
				V2_GPIOC_next[regbit] |= (((~V2_GPIOC_next[regbit]) & 0x1800) << 16);

				regbit++;
				databit--;
			}
		}
		else // no data left in the buffer
		{
			if(c == CONSOLE_NES)
			{
				databit = 7; // number of bits of NES - 1
			}
			else
			{
				databit = 15; // number of bits of SNES - 1
			}

			// no controller data means all pins get set high for this protocol
			for(uint8_t index = 0;index <= databit;index++)
			{
				P1_GPIOC_next[index] = (1 << P1_D0_HIGH_C) | (1 << P1_D1_HIGH_C) | (1 << P1_D2_HIGH_C);
				P2_GPIOC_next[index] = (1 << P2_D0_HIGH_C) | (1 << P2_D1_HIGH_C) | (1 << P2_D2_HIGH_C);

				V1_GPIOB_next[index] = (1 << V1_D0_LOW_B) | (1 << V1_D1_LOW_B);
				V2_GPIOC_next[index] = (1 << V2_D0_LOW_C) | (1 << V2_D1_LOW_C);
			}
		}

		if(TASRunIsInitialized(tasrun))
		{
			if(bulk_mode)
			{
				if(!request_pending && TASRunGetSize(tasrun) <= (MAX_SIZE-28)) // not full enough
				{
					if(serial_interface_output((uint8_t*)"a", 1) == USBD_OK) // notify that we latched and want more
					{
						request_pending = 1;
					}
				}
			}
			else
			{
				serial_interface_output((uint8_t*)"A", 1); // notify that we latched
			}
		}
		else
		{
			if(c == CONSOLE_NES)
				regbit = 8;
			else
				regbit = 16;

			// fill the overread
			if(TASRunGetOverread(tasrun)) // overread is 1/HIGH
			{
				// so set logical LOW (NES/SNES button pressed)
				for(uint8_t index = regbit;index < 17;index++)
				{
					P1_GPIOC_current[index] = P1_GPIOC_next[index] = (1 << P1_D0_LOW_C) | (1 << P1_D1_LOW_C) | (1 << P1_D2_LOW_C);
					P2_GPIOC_current[index] = P2_GPIOC_next[index] = (1 << P2_D0_LOW_C) | (1 << P2_D1_LOW_C) | (1 << P2_D2_LOW_C);
				}
			}
			else
			{
				for(uint8_t index = regbit;index < 17;index++)
				{
					P1_GPIOC_current[index] = P1_GPIOC_next[index] = (1 << P1_D0_HIGH_C) | (1 << P1_D1_HIGH_C) | (1 << P1_D2_HIGH_C);
					P2_GPIOC_current[index] = P2_GPIOC_next[index] = (1 << P2_D0_HIGH_C) | (1 << P2_D1_HIGH_C) | (1 << P2_D2_HIGH_C);
				}
			}
		}

		// vis board code = 16 clock pulses followed by a latch pulse
		memcpy((uint32_t*)&V1_GPIOB_current, (uint32_t*)&V1_GPIOB_next, 64);
		memcpy((uint32_t*)&V2_GPIOC_current, (uint32_t*)&V2_GPIOC_next, 64);
		UpdateVisBoards();
	}
	else if(recentLatch == 1) // multiple close latches and DPCM fix is enabled
	{
		__disable_irq();
		// repeat the same frame of input
		//GPIOC->BSRR = P1_GPIOC_current[0] | P2_GPIOC_current[0] | V2_GPIOC_current[0];
		GPIOC->BSRR = (P1_GPIOC_current[0] & 0x00080008) | P2_GPIOC_current[0];
		GPIOC->BSRR = (P1_GPIOC_current[0] & 0x00040004);

		p1_current_bit = p2_current_bit = 1;
		__enable_irq();

		ResetAndEnableTrainTimer();
	}

  /* USER CODE END EXTI1_IRQn 0 */
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_1);
  /* USER CODE BEGIN EXTI1_IRQn 1 */

  /* USER CODE END EXTI1_IRQn 1 */
}

/**
  * @brief This function handles EXTI line 4 interrupt.
  */
void EXTI4_IRQHandler(void)
{
  /* USER CODE BEGIN EXTI4_IRQn 0 */
	GCN64CommandStart(0);
  /* USER CODE END EXTI4_IRQn 0 */
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_4);
  /* USER CODE BEGIN EXTI4_IRQn 1 */

  /* USER CODE END EXTI4_IRQn 1 */
}

/**
  * @brief This function handles EXTI line[9:5] interrupts.
  */
void EXTI9_5_IRQHandler(void)
{
  /* USER CODE BEGIN EXTI9_5_IRQn 0 */
	TASRun *tasrun = TASRunGetByIndex(RUN_A);
	Console c = TASRunGetConsole(tasrun);
	if(c == CONSOLE_N64 || c == CONSOLE_GC || c == CONSOLE_Z64TC)
	{
		if(__HAL_GPIO_EXTI_GET_IT(P2_DATA_2_Pin))
		{
			GCN64CommandStart(1);
		}
		else if(__HAL_GPIO_EXTI_GET_IT(V1_DATA_0_Pin))
		{
			GCN64CommandStart(2);
		}
		else
		{
			Error_Handler();
		}
	}
	else
	{
		// P2_CLOCK
		if(!p2_clock_filtered && p2_current_bit < 17) // sanity check... but 32 or more bits should never be read in a single latch!
		{
			if(clockFix)
			{
				my_wait_us_asm(2); // necessary to prevent switching too fast in DPCM fix mode
			}

			GPIOC->BSRR = P2_GPIOC_current[p2_current_bit];

			ResetAndEnableP2ClockTimer();
			p2_current_bit++;
		}
	}
  /* USER CODE END EXTI9_5_IRQn 0 */
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_5);
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_7);
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_9);
  /* USER CODE BEGIN EXTI9_5_IRQn 1 */

  /* USER CODE END EXTI9_5_IRQn 1 */
}

/**
  * @brief This function handles TIM1 update interrupt and TIM10 global interrupt.
  */
void TIM1_UP_TIM10_IRQHandler(void)
{
  /* USER CODE BEGIN TIM1_UP_TIM10_IRQn 0 */
  between_trains = 1; // if the timer expired, there was at least 20ms between latches. therefore we are between trains.
  DisableTrainTimer(); // to ensure it was a 1-shot

  /* USER CODE END TIM1_UP_TIM10_IRQn 0 */
  HAL_TIM_IRQHandler(&htim10);
  /* USER CODE BEGIN TIM1_UP_TIM10_IRQn 1 */

  /* USER CODE END TIM1_UP_TIM10_IRQn 1 */
}

/**
  * @brief This function handles TIM3 global interrupt.
  */
void TIM3_IRQHandler(void)
{
  /* USER CODE BEGIN TIM3_IRQn 0 */
  // This is a latch timer
  recentLatch = 0;
  Disable8msTimer(); // to ensure it was a 1-shot

  /* USER CODE END TIM3_IRQn 0 */
  HAL_TIM_IRQHandler(&htim3);
  /* USER CODE BEGIN TIM3_IRQn 1 */

  /* USER CODE END TIM3_IRQn 1 */
}

/**
  * @brief This function handles USART2 global interrupt.
  */
void USART2_IRQHandler(void)
{
  /* USER CODE BEGIN USART2_IRQn 0 */
	uint32_t isrflags   = READ_REG(huart2.Instance->SR);
	uint32_t cr1its     = READ_REG(huart2.Instance->CR1);
	/* UART in mode Transmitter ------------------------------------------------*/
	if (((isrflags & USART_SR_TXE) != RESET) && ((cr1its & USART_CR1_TXEIE) != RESET))
	{
		Simple_Transmit(&huart2);
		return;
	}

	/* UART in mode Transmitter end --------------------------------------------*/
	if (((isrflags & USART_SR_TC) != RESET) && ((cr1its & USART_CR1_TCIE) != RESET))
	{
		/* Disable the UART Transmit Complete Interrupt */
		__HAL_UART_DISABLE_IT(&huart2, UART_IT_TC);

		/* Tx process is ended, restore huart->gState to Ready */
		huart2.gState = HAL_UART_STATE_READY;
		return;
	}

	if(((isrflags & USART_SR_RXNE) != RESET) && ((cr1its & USART_CR1_RXNEIE) != RESET))
	{
		// PROCESS USART2 Rx IRQ HERE
		uint8_t input = ((huart2.Instance)->DR) & (uint8_t)0xFF; // get the last byte from the data register

		serial_interface_set_output_function(UART2_OutputFunction);
		serial_interface_consume(&input, 1);
		return;
	}
  /* USER CODE END USART2_IRQn 0 */
  HAL_UART_IRQHandler(&huart2);
  /* USER CODE BEGIN USART2_IRQn 1 */

  /* USER CODE END USART2_IRQn 1 */
}

/**
  * @brief This function handles EXTI line[15:10] interrupts.
  */
void EXTI15_10_IRQHandler(void)
{
  /* USER CODE BEGIN EXTI15_10_IRQn 0 */
	GCN64CommandStart(3);

  /* USER CODE END EXTI15_10_IRQn 0 */
  HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_12);
  /* USER CODE BEGIN EXTI15_10_IRQn 1 */

  /* USER CODE END EXTI15_10_IRQn 1 */
}

/**
  * @brief This function handles TIM6 global interrupt and DAC1, DAC2 underrun error interrupts.
  */
void TIM6_DAC_IRQHandler(void)
{
  /* USER CODE BEGIN TIM6_DAC_IRQn 0 */
  // This is a variable clock timer for P1
  p1_clock_filtered = 0;
  DisableP1ClockTimer(); // to ensure it was a 1-shot
  /* USER CODE END TIM6_DAC_IRQn 0 */
  HAL_TIM_IRQHandler(&htim6);
  /* USER CODE BEGIN TIM6_DAC_IRQn 1 */

  /* USER CODE END TIM6_DAC_IRQn 1 */
}

/**
  * @brief This function handles TIM7 global interrupt.
  */
void TIM7_IRQHandler(void)
{
  /* USER CODE BEGIN TIM7_IRQn 0 */
  // This is a variable clock timer for P2
  p2_clock_filtered = 0;
  DisableP2ClockTimer(); // to ensure it was a 1-shot
  /* USER CODE END TIM7_IRQn 0 */
  HAL_TIM_IRQHandler(&htim7);
  /* USER CODE BEGIN TIM7_IRQn 1 */

  /* USER CODE END TIM7_IRQn 1 */
}

/**
  * @brief This function handles USB On The Go FS global interrupt.
  */
void OTG_FS_IRQHandler(void)
{
  /* USER CODE BEGIN OTG_FS_IRQn 0 */

  /* USER CODE END OTG_FS_IRQn 0 */
  HAL_PCD_IRQHandler(&hpcd_USB_OTG_FS);
  /* USER CODE BEGIN OTG_FS_IRQn 1 */

  /* USER CODE END OTG_FS_IRQn 1 */
}

/* USER CODE BEGIN 1 */
HAL_StatusTypeDef Simple_Transmit(UART_HandleTypeDef *huart)
{
  /* Check that a Tx process is ongoing */
  if (huart->gState == HAL_UART_STATE_BUSY_TX)
  {
    huart->Instance->DR = (uint8_t)(*huart->pTxBuffPtr++ & (uint8_t)0x00FF);

    if (--huart->TxXferCount == 0U)
    {
      /* Disable the UART Transmit Complete Interrupt */
      __HAL_UART_DISABLE_IT(huart, UART_IT_TXE);

      /* Enable the UART Transmit Complete Interrupt */
      __HAL_UART_ENABLE_IT(huart, UART_IT_TC);
    }
    return HAL_OK;
  }
  else
  {
    return HAL_BUSY;
  }
}

void DisableTrainTimer()
{
	TIM10->CNT = 0; // reset count
	TIM10->SR = 0; // reset flags

	HAL_TIM_Base_Stop_IT(&htim10);
}

void ResetAndEnableTrainTimer()
{
	HAL_TIM_Base_Start_IT(&htim10);
}

void Disable8msTimer()
{
	TIM3->CNT = 0; // reset count
	TIM3->SR = 0; // reset flags

	HAL_TIM_Base_Stop_IT(&htim3);
}

void ResetAndEnable8msTimer()
{
	HAL_TIM_Base_Start_IT(&htim3);
}

void DisableP1ClockTimer()
{
	TIM6->CNT = 0; // reset count
	TIM6->SR = 0; // reset flags

	HAL_TIM_Base_Stop_IT(&htim6);
}

void ResetAndEnableP1ClockTimer()
{
	if(clockFix == 0)
	{
		return;
	}

	p1_clock_filtered = 1;

	HAL_TIM_Base_Start_IT(&htim6);
}

void DisableP2ClockTimer()
{
	TIM7->CNT = 0; // reset count
	TIM7->SR = 0; // reset flags

	HAL_TIM_Base_Stop_IT(&htim7);
}

void ResetAndEnableP2ClockTimer()
{
	if(clockFix == 0)
	{
		return;
	}

	p2_clock_filtered = 1;

	HAL_TIM_Base_Start_IT(&htim7);
}

__attribute__((optimize("O0"))) inline void UpdateVisBoards()
{
	if(c == CONSOLE_NES)
	{
		// first 8 clock pulses at least 10ns in width
		for(int x = 0;x < 8;x++)
		{
			//set vis data
			GPIOB->BSRR = V1_GPIOB_current[x];
			GPIOC->BSRR = V2_GPIOC_current[x];

			// give time to it to register
			WAIT_4_CYCLES;

			GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
			GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
			// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
			WAIT_4_CYCLES;
			GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
			GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
			WAIT_4_CYCLES;
		}

		// set rest of the vis data to 0s
		GPIOB->BSRR = (1 << V1_D0_LOW_B) | (1 << V1_D1_LOW_B);
		GPIOC->BSRR = (1 << V2_D0_LOW_C) | (1 << V2_D1_LOW_C);

		WAIT_4_CYCLES;

		for(int x = 0;x < 8;x++)
		{
			GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
			GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
			// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
			WAIT_4_CYCLES;
			GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
			GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
			WAIT_4_CYCLES;
		}
	}
	else if(c == CONSOLE_SNES)
	{
		// fix bit order

		GPIOB->BSRR = V1_GPIOB_current[8];
		GPIOC->BSRR = V2_GPIOC_current[8];

		// give time to it to register
		WAIT_4_CYCLES;

		GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
		GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
		// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
		WAIT_4_CYCLES;
		GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
		GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
		WAIT_4_CYCLES;

		GPIOB->BSRR = V1_GPIOB_current[0];
		GPIOC->BSRR = V2_GPIOC_current[0];

		// give time to it to register
		WAIT_4_CYCLES;

		GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
		GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
		// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
		WAIT_4_CYCLES;
		GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
		GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
		WAIT_4_CYCLES;

		// at least 10ns in width
		for(int x = 2;x < 8;x++)
		{
			//set vis data
			GPIOB->BSRR = V1_GPIOB_current[x];
			GPIOC->BSRR = V2_GPIOC_current[x];

			// give time to it to register
			WAIT_4_CYCLES;

			GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
			GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
			// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
			WAIT_4_CYCLES;
			GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
			GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
			WAIT_4_CYCLES;
		}

		GPIOB->BSRR = V1_GPIOB_current[9];
		GPIOC->BSRR = V2_GPIOC_current[9];

		// give time to it to register
		WAIT_4_CYCLES;

		GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
		GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
		// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
		WAIT_4_CYCLES;
		GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
		GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
		WAIT_4_CYCLES;

		GPIOB->BSRR = V1_GPIOB_current[1];
		GPIOC->BSRR = V2_GPIOC_current[1];

		// give time to it to register
		WAIT_4_CYCLES;

		GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
		GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
		// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
		WAIT_4_CYCLES;
		GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
		GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
		WAIT_4_CYCLES;

		// at least 10ns in width
		for(int x = 10;x < 16;x++)
		{
			//set vis data
			GPIOB->BSRR = V1_GPIOB_current[x];
			GPIOC->BSRR = V2_GPIOC_current[x];

			// give time to it to register
			WAIT_4_CYCLES;

			GPIOB->BSRR = (1 << V1_CLOCK_HIGH_B);
			GPIOA->BSRR = (1 << V2_CLOCK_HIGH_A);
			// wait 4 cycles which should be well over the minimum required 10ns but still relatively quick
			WAIT_4_CYCLES;
			GPIOB->BSRR = (1 << V1_CLOCK_LOW_B);
			GPIOA->BSRR = (1 << V2_CLOCK_LOW_A);
			WAIT_4_CYCLES;
		}

	}
	WAIT_4_CYCLES;

	// create at least a 20ns latch pulse (this should be about 40ns)
	GPIOB->BSRR = (1 << V1_LATCH_HIGH_B);
	GPIOC->BSRR = (1 << V2_LATCH_HIGH_C);
	WAIT_4_CYCLES;
	WAIT_4_CYCLES;
	GPIOB->BSRR = (1 << V1_LATCH_LOW_B);
	GPIOC->BSRR = (1 << V2_LATCH_LOW_C);
}

uint8_t UART2_OutputFunction(uint8_t *buffer, uint16_t n)
{
	return HAL_UART_Transmit_IT(&huart2, buffer, n);
}

static uint8_t GCN64_ValidatePoll(TASRun *tasrun, uint8_t player, uint8_t *result, uint8_t *resultlen)
{
	*resultlen = 0;
	uint8_t ret = 1; //Current tasrun data is valid
	if(tasrun->size == 0)
	{
		result[0] = 0xB2; //buffer underflow
		*resultlen = 1;
		return 0;
	}
	uint8_t lastplayer = tasrun->gcn64_lastControllerPolled;
	if(player >= lastplayer)
	{
		GetNextFrame(tasrun);
		result[0] = 'A';
		*resultlen = 1;
		if(tasrun->size == 0)
		{
			result[1] = 0xB3; //buffer just emptied
			*resultlen = 2;
			ret = 0;
		}
	}
	tasrun->gcn64_lastControllerPolled = player;
	uint8_t expectedplayer = lastplayer - 1;
	for(int i=0; i<5; ++i)
	{
		if(i == 4)
		{
			expectedplayer = 0xFF; //error
			break;
		}
		if(expectedplayer >= 4)
		{
			expectedplayer = 3;
		}
		if(tasrun->controllersBitmask & (1 << (7 - expectedplayer)))
		{
			break;
		}
		--expectedplayer;
	}
	if(player != expectedplayer)
	{
		result[3] = result[0]; //in case there was 'A'
		result[4] = result[1]; //in case there was B3
		result[0] = 0xC3;
		result[1] = player;
		result[2] = expectedplayer;
		*resultlen += 3;
	}
	return ret;
}

static uint8_t last_send_result = 0;
static uint8_t result[8];

void GCN64CommandStart(uint8_t player)
{
	__disable_irq();

	TASRun *tasrun = TASRunGetByIndex(RUN_A);
	Console c = TASRunGetConsole(tasrun);

	int8_t cmd_bytes = GCN64_ReadCommand(player);
	uint8_t cmd = gcn64_cmd_buffer[0];
	my_wait_us_asm(2); // wait a small amount of time before replying

	/*
	 * 'A': valid run command (not error)
	 * 0xB2 (0): buffer underflow
	 * 0xB3 (0): buffer just emptied (not error)
	 * 0xC0 (3): command receive error
	 * 0xC1 (3): command bad length
	 * 0xC2 (3): unsupported command
	 * 0xC3 (2): players out of order
	 * 0xC4 (1): identity command (not error)
	 * 0xC5 (1): reset/origin command (not error)
	 * 0xC6 (3): mempak read (not error)
	 * 0xC7 (4): mempak write (not error)
	 *       ^ number of additional data bytes
	 */
	result[0] = 0xC2;
	result[1] = player;
	result[2] = cmd;
	result[3] = cmd_bytes;
	uint8_t resultlen = 4;

	//-------- SEND RESPONSE
	GCN64_SetPortOutput(player);

	if(cmd_bytes < 0){
		result[0] = 0xC0;
		result[3] = gcn64_cmd_buffer[1];
		result[4] = gcn64_cmd_buffer[2];
		resultlen = 5;
	}else if(c == CONSOLE_N64 || c == CONSOLE_Z64TC){
		if(cmd == 0x00){
			//N64 identity
			if(cmd_bytes != 1){
				result[0] = 0xC1;
			}else{
				result[0] = 0xC4;
				resultlen = 2;
				N64_SendIdentity(player, c == CONSOLE_Z64TC ? 1 : 2);
				if(c == CONSOLE_Z64TC) TC_Got_Identity(tasrun, player);
			}
		}else if(cmd == 0xFF){
			//N64 reset
			if(cmd_bytes != 1){
				result[0] = 0xC1;
			}else{
				result[0] = 0xC5;
				resultlen = 2;
				N64_SendIdentity(player, c == CONSOLE_Z64TC ? 1 : 2);
				if(c == CONSOLE_Z64TC) TC_Got_Reset(tasrun, player);
			}
		}else if(cmd == 0x01){
			//N64 poll
			if(cmd_bytes != 1){
				result[0] = 0xC1;
			}else if(c == CONSOLE_Z64TC){
				TC_Poll(tasrun, player);
				result[0] = 'A';
				resultlen = 2;
			}else if(GCN64_ValidatePoll(tasrun, player, result, &resultlen)){
				GCN64_SendData((uint8_t*)&((*tasrun->current)[player][0].n64_data), 4, player);
			}else{
				N64_SendDefaultInput(player); //buffer underflow or empty
			}
		}else if(cmd == 0x02){
			//N64 mempak read
			result[0] = 0xC6;
			result[2] = gcn64_cmd_buffer[1];
			result[3] = gcn64_cmd_buffer[2];
			resultlen = 4;
			if(c == CONSOLE_Z64TC) TC_MempakRead(tasrun, player, cmd_bytes, result, &resultlen);
		}else if(cmd == 0x03){
			//N64 mempak write
			result[0] = 0xC7;
			result[2] = gcn64_cmd_buffer[1];
			result[3] = gcn64_cmd_buffer[2];
			result[4] = gcn64_cmd_buffer[3];
			resultlen = 5;
			if(c == CONSOLE_Z64TC) TC_MempakWrite(tasrun, player, cmd_bytes, result, &resultlen);
		}
	}
	else if(c == CONSOLE_GC)
	{
		if(cmd == 0x00){
			//GC identity
			if(cmd_bytes != 1){
				result[0] = 0xC1;
			}else{
				result[0] = 0xC4;
				resultlen = 2;
				GCN_SendIdentity(player);
			}
		}else if(cmd == 0x41){
			//GC origin
			if(cmd_bytes != 1){
				result[0] = 0xC1;
			}else{
				result[0] = 0xC5;
				resultlen = 2;
				GCN_SendOrigin(player);
			}
		}else if(cmd == 0x40 && gcn64_cmd_buffer[1] == 0x03 && gcn64_cmd_buffer[2] <= 2){
			//GC poll
			if(GCN64_ValidatePoll(tasrun, player, result, &resultlen))
			{
				(*tasrun->current)[player][0].gc_data.beginning_one = 1;
				GCN64_SendData((uint8_t*)&((*tasrun->current)[player][0].gc_data), 8, player);
			}
			else
			{
				GCN_SendDefaultInput(player); //buffer underflow or empty
			}
		}
	}

	//-------- DONE SENDING RESPONSE

	GCN64_SetPortInput(player);
	__enable_irq();

	/*
	if(c != CONSOLE_Z64TC){
		result[resultlen++] = '1' + player;
		//if(last_send_result){
		//	result[resultlen++] = last_send_result;
		//}
	}
	*/

	if((result[0] == 0xC4 || result[0] == 'A') && resultlen == 2){
		return; //No need to spam identity/poll
	}

	if(resultlen) {
		last_send_result = serial_interface_output(result, resultlen);
	}

}

/* USER CODE END 1 */
/************************ (C) COPYRIGHT STMicroelectronics *****END OF FILE****/
