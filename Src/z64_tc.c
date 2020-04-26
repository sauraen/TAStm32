/*
 * z64_tc.c
 *
 * Zelda 64 Total Control data interface
 */

#include "z64_tc.h"

void TC_Reset(TASRun *tasrun) {
	__disable_irq();

	tasrun->tc_cmd_read = 0;
	tasrun->tc_cmd_write = 0;
	tasrun->tc_cmds_avail = 0;
	tasrun->tc_byte_read = 0;
	tasrun->tc_byte_write = 0;

	tasrun->tc_nextctrlr = 3;
	tasrun->tc_state = 0xFF;
	tasrun->tc_rumble_response = 0;
	tasrun->tc_rumble_rec_mask = 0;

	__enable_irq();
}

uint8_t TC_Validate_NewCmd(TASRun *tasrun){
	uint8_t ret = 0;
	__disable_irq();
	if(tasrun->tc_byte_write != 0) ret = 0x98;
	if(tasrun->tc_cmds_avail >= TC_MAX_COMMANDS) ret = 0x99;
	__enable_irq();
	return ret;
}

uint8_t TC_RecCmdByte(TASRun *tasrun, uint8_t input){
	__disable_irq();
	tasrun->tcData[tasrun->tc_cmd_write][tasrun->tc_byte_write] = input;
	if(++tasrun->tc_byte_write < TC_COMMAND_SIZE){
		__enable_irq();
		return 0;
	}
	tasrun->tc_byte_write = 0;
	++tasrun->tc_cmd_write;
	if(tasrun->tc_cmd_write >= TC_MAX_COMMANDS) tasrun->tc_cmd_write = 0;
	++tasrun->tc_cmds_avail;
	__enable_irq();
	return 1;
}

#define NEXT_CTRLR(player) (((player) == 1) ? 3 : (player) - 1)

void TC_Got_Identity(TASRun *tasrun, uint8_t player){
	tasrun->tc_state = 0;
	tasrun->tc_nextctrlr = NEXT_CTRLR(player);
}
void TC_Got_Reset(TASRun *tasrun, uint8_t player){
	//Should not happen during our run
	tasrun->tc_state = 0xFF;
	tasrun->tc_nextctrlr = NEXT_CTRLR(player);
}

void TC_Poll(TASRun *tasrun, uint8_t player){
	if(tasrun->tc_nextctrlr == player && tasrun->tc_cmds_avail > 0){
		if(tasrun->tc_state <= 1 && player == 3){
			//Either just did rumble or just did identity (there was no rumble)
			tasrun->tc_state = 2;
			tasrun->tc_byte_read = 0;
		}
		if(tasrun->tc_state == 2){
			//Normal poll
			GCN64_SendData(&tasrun->tcData[tasrun->tc_cmd_read][tasrun->tc_byte_read], 4, player);
			tasrun->tc_byte_read += 4;
			if(tasrun->tc_byte_read >= TC_COMMAND_SIZE){
				tasrun->tc_state = 0xFF;
				tasrun->tc_byte_read = 0;
				++tasrun->tc_cmd_read;
				if(tasrun->tc_cmd_read >= TC_MAX_COMMANDS) tasrun->tc_cmd_read = 0;
				--tasrun->tc_cmds_avail;
			}
			tasrun->tc_nextctrlr = NEXT_CTRLR(player);
			return;
		}
	}
	tasrun->tc_state = 0xFF;
	tasrun->tc_nextctrlr = NEXT_CTRLR(player);
	N64_SendDefaultInput(player);
}

#define GET_MEMPAK_ADDR \
	uint16_t addr_main = ((uint16_t)gcn64_cmd_buffer[1] << 8) | gcn64_cmd_buffer[2]; \
	uint16_t addr_short = addr_main >> 5; \
	if(osMempakAddrCRC(addr_short) != (addr_main & 0x1F)){ \
		/*Bad addr CRC*/ \
		result[(*resultlen)++] = 0x9C; \
	}

void TC_MempakRead(TASRun *tasrun, uint8_t player, int8_t cmd_bytes, uint8_t *result, uint8_t *resultlen){
	/*
	 * Probe process:
	 * N64: [0xFE] * 0x20 -> 0x8000 (0x400)
	 * Mempak: 0x8000 -> [something with correct checksum][0x1F] = 0xFE for mempak, else continue
	 * N64: [0x80] * 0x20 -> 0x8000 (0x400)
	 * Mempak: 0x8000 -> [something with correct checksum][0x1F] = 0x80 for rumble pak, else mempak
	 * Rumble process:
	 * N64: [0x01 or 0x00 for rumble on/off] * 0x20 -> 0xC000 (0x600)
	 * (No reply)
	 * Rumble happens in order of controllers 0-3, but probing happens over multiple frames
	 * (only one controller per frame is probed, except when rumble is supposed to stop
	 * in which case all four are in order 0-3)
	 */
	*resultlen = 0;
	//Result already has: Mempak write, player, addr hi, addr lo
	if(cmd_bytes != 3){
		result[(*resultlen)++] = 0x9A;
		return;
	}
	GET_MEMPAK_ADDR
	tasrun->tc_rumble_rec_mask = 0;
	if(addr_short == 0x400){
		//0x20 bytes of something where 0x1F is 0x80
		//byte 0x20 must be correct checksum
		for(int i=0; i<0x20; ++i){
			gcn64_cmd_buffer[i] = 0x80;
		}
		gcn64_cmd_buffer[0x20] = osMempakDataCRC(gcn64_cmd_buffer);
		GCN64_SendData(gcn64_cmd_buffer, 0x21, player);
	}
}
void TC_MempakWrite(TASRun *tasrun, uint8_t player, int8_t cmd_bytes, uint8_t *result, uint8_t *resultlen){
	//Result already has: Mempak write, player, addr hi, addr lo, data 0
	*resultlen = 0;
	if(cmd_bytes != 0x23){
		result[(*resultlen)++] = 0x9B;
		return;
	}
	GET_MEMPAK_ADDR
	gcn64_cmd_buffer[0x23] = osMempakDataCRC(&gcn64_cmd_buffer[3]);
	GCN64_SendData(&gcn64_cmd_buffer[0x23], 1, player);
	if(addr_short == 0x600){
		//Rumble write
		uint8_t rumble = gcn64_cmd_buffer[3];
		if(rumble & 0xFE){
			//Supposed to be only 0 or 1
			result[(*resultlen)++] = 0x9D;
		}
		rumble &= 1;
		if(tasrun->tc_state == 0){
			tasrun->tc_rumble_rec_mask = 0;
			tasrun->tc_rumble_response = 0;
			tasrun->tc_state = 1;
		}
		tasrun->tc_rumble_rec_mask |= 1 << (player - 1);
		tasrun->tc_rumble_response |= rumble << (player - 1);
		if(tasrun->tc_rumble_rec_mask == 7){
			//Send response to host
			result[(*resultlen)++] = 0x90 | tasrun->tc_rumble_response;
		}
	}else{
		tasrun->tc_rumble_rec_mask = 0;
	}
}
