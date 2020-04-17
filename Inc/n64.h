#ifndef __N64__H
#define __N64__H

#include "main.h"

typedef struct __attribute__((packed))
{
	unsigned int right : 1; // low bit of 1st byte
	unsigned int left : 1;
	unsigned int down : 1;
	unsigned int up : 1;
	unsigned int start : 1;
	unsigned int z : 1;
	unsigned int b : 1;
	unsigned int a : 1; // high bit of 1st byte

	unsigned int c_right : 1;
	unsigned int c_left : 1;
	unsigned int c_down : 1;
	unsigned int c_up : 1;
	unsigned int r : 1;
    unsigned int l : 1;
    unsigned int dummy1 : 1;
    unsigned int dummy2 : 1;

    char x_axis;

    char y_axis;

} N64ControllerData;

typedef struct __attribute__((packed))
{
	unsigned int a : 1;
	unsigned int b : 1;
	unsigned int x : 1; // 1 bit wide
	unsigned int y : 1;
	unsigned int start : 1;
	unsigned int beginning_zeros : 3;

    unsigned int d_left : 1;
    unsigned int d_right : 1;
    unsigned int d_down : 1;
    unsigned int d_up : 1;
    unsigned int z : 1;
    unsigned int r : 1;
    unsigned int l : 1;
    unsigned int beginning_one : 1;

    uint8_t a_x_axis;
    uint8_t a_y_axis;
    uint8_t c_x_axis;
    uint8_t c_y_axis;
    uint8_t l_trigger;
    uint8_t r_trigger;

} GCControllerData; // all bits are in the correct order... except for the analog

extern GPIO_TypeDef* const GCN64_Ctrlr_Port[4];
extern const uint32_t GCN64_Ctrlr_Pin[4];
extern const uint32_t GCN64_Ctrlr_InMask[4];
extern const uint32_t GCN64_Ctrlr_OutSet[4];

maybe_unused static void GCN64_SetPortInput(uint8_t player)
{
	GCN64_Ctrlr_Port[player]->MODER &= GCN64_Ctrlr_InMask[player];
}

maybe_unused static void GCN64_SetPortOutput(uint8_t player)
{
	GCN64_Ctrlr_Port[player]->MODER |= GCN64_Ctrlr_OutSet[player];
}

maybe_unused static void GCN64_Send0(uint8_t player)
{
	GCN64_Ctrlr_Port[player]->BSRR = GCN64_Ctrlr_Pin[player]<<16;
	my_wait_us_asm(3);
	GCN64_Ctrlr_Port[player]->BSRR = GCN64_Ctrlr_Pin[player];
	my_wait_us_asm(1);
}
maybe_unused static void GCN64_Send1(uint8_t player)
{
	GCN64_Ctrlr_Port[player]->BSRR = GCN64_Ctrlr_Pin[player]<<16;
	my_wait_us_asm(1);
	GCN64_Ctrlr_Port[player]->BSRR = GCN64_Ctrlr_Pin[player];
	my_wait_us_asm(3);
}
maybe_unused static void GCN64_SendStop(uint8_t player)
{
	GCN64_Ctrlr_Port[player]->BSRR = GCN64_Ctrlr_Pin[player]<<16;
	my_wait_us_asm(1);
	GCN64_Ctrlr_Port[player]->BSRR = GCN64_Ctrlr_Pin[player];
}
maybe_unused static void GCN64_SendData(uint8_t *data, uint8_t bytes, uint8_t player)
{
	while(bytes){
		uint8_t d = *data;
		for(uint8_t b=0; b<8; ++b){
			(d & 0x80) ? GCN64_Send1(player) : GCN64_Send0(player);
			d <<= 1;
		}
		++data;
		--bytes;
	}
	GCN64_SendStop(player);
}

int8_t GCN64_ReadCommand(uint8_t player);
extern uint8_t gcn64_cmd_buffer[0x25];

void N64_SendIdentity(uint8_t player, uint8_t ctrlr_status = 0x2);
void GCN_SendIdentity(uint8_t player);
void N64_SendDefaultInput(uint8_t player);
void GCN_SendDefaultInput(uint8_t player);
void GCN_SendOrigin(uint8_t player);

extern uint8_t osMempakAddrCRC(uint16_t addr);
extern uint8_t osMempakDataCRC(uint8_t* data);

#endif
