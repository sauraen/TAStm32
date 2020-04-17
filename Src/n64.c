#include <stdint.h>
#include <string.h>
#include "n64.h"
#include "stm32f4xx_hal.h"
#include "main.h"


GPIO_TypeDef* const GCN64_Ctrlr_Port[4] = {
	P1_DATA_2_GPIO_Port,
	P2_DATA_2_GPIO_Port,
	V1_DATA_0_GPIO_Port,
	V2_DATA_0_GPIO_Port
};
const uint32_t GCN64_Ctrlr_Pin[4] = {
	P1_DATA_2_Pin,
	P2_DATA_2_Pin,
	V1_DATA_0_Pin,
	V2_DATA_0_Pin
};
const uint32_t GCN64_Ctrlr_InMask[4] = {
	~(0x3*(uint32_t)P1_DATA_2_Pin*P1_DATA_2_Pin),
	~(0x3*(uint32_t)P2_DATA_2_Pin*P2_DATA_2_Pin),
	~(0x3*(uint32_t)V1_DATA_0_Pin*V1_DATA_0_Pin),
	~(0x3*(uint32_t)V2_DATA_0_Pin*V2_DATA_0_Pin)
};
const uint32_t GCN64_Ctrlr_OutSet[4] = {
	GPIO_MODE_OUTPUT_PP*(uint32_t)P1_DATA_2_Pin*P1_DATA_2_Pin,
	GPIO_MODE_OUTPUT_PP*(uint32_t)P2_DATA_2_Pin*P2_DATA_2_Pin,
	GPIO_MODE_OUTPUT_PP*(uint32_t)V1_DATA_0_Pin*V1_DATA_0_Pin,
	GPIO_MODE_OUTPUT_PP*(uint32_t)V2_DATA_0_Pin*V2_DATA_0_Pin
};

// N64 data pin is p1_d2
#define N64_READ (GCN64_Ctrlr_Port[player]->IDR & GCN64_Ctrlr_Pin[player])

static uint8_t GetMiddleOfPulse(uint8_t player)
{
	uint8_t ct = 0;
    // wait for line to go high
    while(1)
    {
        if(N64_READ) break;

        ct++;
        if(ct == 200) // failsafe limit TBD
        	return 5; // error code
    }

    ct = 0;

    // wait for line to go low
    while(1)
    {
        if(!N64_READ) break;

        ct++;
		if(ct == 200) // failsafe limit TBD
			return 5; // error code
    }

    // now we have the falling edge

    // wait 2 microseconds to be in the middle of the pulse, and read. high --> 1.  low --> 0.
    my_wait_us_asm(2);

    return N64_READ ? 1U : 0U;
}

uint8_t gcn64_cmd_buffer[0x25];

/*
uint32_t GCN64_ReadCommand(uint8_t player)
{
	uint8_t retVal;

	// we are already at the first falling edge
	// get middle of first pulse, 2us later
	// however, some time has elapsed for the ISR and at least 2 non-inlined function calls
	my_wait_100ns_asm(15);
	uint32_t command = N64_READ ? 1U : 0U, bits_read = 1;

    while(1) // read at least 9 bits (1 byte + stop bit)
    {
        command = command << 1; // make room for the new bit
        retVal = GetMiddleOfPulse(player);
        if(retVal == 5) // timeout
        {
        	if(bits_read >= 8)
        	{
				command = command >> 2; // get rid of the stop bit AND the room we made for an additional bit
				return command;
        	}
        	else // there is no possible way this can be a real command
        	{
        		return 5; // dummy value
        	}
        }
        command += retVal;

        bits_read++;

        if(bits_read >= 25) // this is the longest known command length
        {
        	command = command >> 1; // get rid of the stop bit (which is always a 1)
        	return command;
        }
    }
}
*/

int8_t GCN64_ReadCommand(uint8_t player)
{
	uint8_t bit = 6;
	uint8_t byte = 0;
	uint8_t bit_read;

	// we are already at the first falling edge
	// get middle of first pulse, 2us later
	// however, some time has elapsed for the ISR and at least 2 non-inlined function calls
	my_wait_100ns_asm(15);
	if(N64_READ) gcn64_cmd_buffer[byte] = 0x80;

	while(1){
		bit_read = GetMiddleOfPulse(player);
		if(bit_read == 5){
			// Timeout
			if(byte >= 1 && bit == 6 && (gcn64_cmd_buffer[byte] & 0x80)){
				// At least one full byte, and stop bit in next byte =
				// Normal end of command
				return byte;
			}else{
				return -1; // Not 8n+1 bits received
			}
			gcn64_cmd_buffer[byte] |= bit_read << bit--;
			if(bit == 255){
				bit = 7;
				++byte;
				if(byte == 25){
					return -2; // Command too long
				}
			}
		}
	}
}

void N64_SendIdentity(uint8_t player, uint8_t ctrlr_status)
{
	// Controller type low-high, then controller status
	// Type: 0x0005 for normal controller (absolute | joyport)
	// Status: 0x1 ctrlr pak connected, 0x2 ctrlr pak disconnected, 0x4 ctrlr pak addr CRC error
	uint32_t data = 0x0005 | ((uint32_t)ctrlr_status) << 16;
	GCN64_SendData((uint8_t*)&data, 3, player);
}

void GCN_SendIdentity(uint8_t player)
{
	// reply 0x90, 0x00, 0x0C
	uint32_t data = 0x000C0090;
	GCN64_SendData((uint8_t*)&data, 3, player);
}

void N64_SendDefaultInput(uint8_t player)
{
	uint32_t data = 0;
	GCN64_SendData((uint8_t*)&data, 4, player);
}
void GCN_SendDefaultInput(uint8_t player)
{
	GCControllerData gc_data = {0};
	gc_data.a_x_axis = 128;
	gc_data.a_y_axis = 128;
	gc_data.c_x_axis = 128;
	gc_data.c_y_axis = 128;
	gc_data.beginning_one = 1;
	GCN64_SendData((uint8_t*)&gc_data, 8, player);
}

void GCN_SendOrigin(uint8_t player)
{
	uint8_t buf[10];
	memset(buf, 0, sizeof(buf));
	GCControllerData *gc_data = (GCControllerData*)&buf[0];

	gc_data->a_x_axis = 128;
	gc_data->a_y_axis = 128;
	gc_data->c_x_axis = 128;
	gc_data->c_y_axis = 128;
	gc_data->beginning_one = 1;

	GCN64_SendData(buf, sizeof(buf), player);
}

// Controller pak CRC functions from libultra, decompiled from OoT

// Valid addr up to 0x7FF
// It's the address of a block of 0x20 bytes in the mempak
uint8_t osMempakAddrCRC(uint16_t addr) {
    uint32_t ret = 0;
    uint16_t bit;
    uint8_t i;

    for (bit = 0x400; bit; bit >>= 1) {
        ret <<= 1;
        if (addr32 & bit) {
            if (ret & 0x20) {
                ret ^= 0x14;
            } else {
                ++ret;
            }
        } else {
            if (ret & 0x20) {
                ret ^= 0x15;
            }
        }
    }
    for (i = 0; i < 5; ++i) {
        ret <<= 1;
        if (ret & 0x20) {
            ret ^= 0x15;
        }
    }
    return ret & 0x1f;
}

uint8_t osMempakDataCRC(uint8_t* data) {
    uint32_t ret = 0;
    uint8_t bit;
    uint8_t byte;

    for (byte = 0x20; byte; --byte, ++data) {
        for (bit = 0x80; bit; bit >>= 1) {
            ret <<= 1;
            if ((*data & bit) != 0) {
                if ((ret & 0x100) != 0) {
                    ret ^= 0x84;
                } else {
                    ++ret;
                }
            } else {
                if (ret & 0x100) {
                    ret ^= 0x85;
                }
            }
        }
    }
    do {
        ret <<= 1;
        if (ret & 0x100) {
            ret ^= 0x85;
        }
        ++byte;
    } while (byte < 8);
    return ret;
}


