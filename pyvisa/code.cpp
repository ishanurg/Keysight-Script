/*
 * TML_MEMS_Single_Current_Temp_Comp_V1.3.cpp
 *
 * Modified for MAX UART SPEED, No CAN Bus
 */ 

#define F_CPU 20000000UL // MAX SPEED: 16 MHz full CPU speed
#define USART0_BAUD_RATE(BAUD_RATE) ((float)(F_CPU * 64 / (16 *(float)BAUD_RATE)) + 0.5)
#define PERIOD_EXAMPLE_VALUE_H (250)
#define DUTY_CYCLE_EXAMPLE_VALUE_H (10)//(227)
#include <avr/io.h>
#include <stdio.h>
#include <string.h>
#include <avr/sfr_defs.h>
#include <stdint.h>
#include <util/delay.h>
#include <avr/interrupt.h>
#include <avr/eeprom.h>
#include <stdint-gcc.h>
#include <avr/sleep.h>
#include <avr/pgmspace.h>
#include <stdbool.h>
#include <stdlib.h>
#include <math.h>
#include <avr/xmega.h> 

#define I2C_TIMEOUT 10000

#define I2C_SCL   (1<<0)
#define I2C_SDA   (1<<1)

#define I2C_STATE_IS_HIGH(x) ((TWI0.MSTATUS & (x)) == (x))
#define I2C_STATE_IS_LOW(x) ((TWI0.MSTATUS & (x)) != (x))
#define I2C_BUS_STATE (TWI0.MSTATUS & TWI_BUSSTATE_gm)

#define I2C_BUS_NOT_IDLE I2C_STATE_IS_LOW(TWI_BUSSTATE_IDLE_gc)
#define I2C_BUS_IDLE I2C_STATE_IS_HIGH(TWI_BUSSTATE_IDLE_gc)

#define I2C_BUS_NOT_BUSY I2C_STATE_IS_LOW(TWI_BUSSTATE_BUSY_gc)
#define I2C_BUS_BUSY I2C_STATE_IS_HIGH(TWI_BUSSTATE_BUSY_gc)

#define I2C_BUS_NOT_OWNER I2C_STATE_IS_LOW(TWI_BUSSTATE_OWNER_gc)
#define I2C_BUS_OWNER I2C_STATE_IS_HIGH(TWI_BUSSTATE_OWNER_gc)

#define I2C_NOT_CLOCKHOLD I2C_STATE_IS_LOW(TWI_CLKHOLD_bm)
#define I2C_CLOCKHOLD I2C_STATE_IS_HIGH(TWI_CLKHOLD_bm)

#define I2C_NOT_BUSERR I2C_STATE_IS_LOW(TWI_BUSERR_bm)
#define I2C_BUSERR I2C_STATE_IS_HIGH(TWI_BUSERR_bm)

#define I2C_NOT_ARBLOST I2C_STATE_IS_LOW(TWI_ARBLOST_bm)
#define I2C_ARBLOST I2C_STATE_IS_HIGH(TWI_ARBLOST_bm)

#define TWI0_BAUD(F_SCL, T_RISE) ((((((float)F_CPU / (float)F_SCL)) - 10 - ((float)F_CPU * T_RISE / 1000000))) / 2)

bool I2C_RawRead(uint8_t ACK);
void InitI2C();
bool I2C_RawStart(uint8_t deviceAddr, uint8_t Direction);
bool I2C_RawWrite(uint8_t write_data);
bool I2C_RawStop(void);
unsigned char I2C_ReadByte(uint8_t address, uint8_t reg);
bool I2C_ReadBytes(uint8_t address, uint8_t reg, uint8_t *data, uint8_t size);
unsigned char I2C_WriteByte(uint8_t address, uint16_t reg, uint8_t data);
bool I2C_WriteBytes(uint8_t address, uint8_t reg, uint8_t data[], uint8_t size);
void I2C_StartMaster();
bool I2C_StopMaster();
bool I2C_StartSlave();
bool I2C_StopSlave();
#define MASTER_ENABLE	1
#define MASTER_DISABLE	0
#define SLAVE_ENABLE	1
#define SLAVE_DISABLE	0
#define I2C_READ 0x01
#define I2C_WRITE 0x00
#define I2C_WAIT_TIMEOUT	10000//0xFF
#define RETURN_OK			0
#define RETURN_FAILED		1
#define RETURN_NO_SLAVE		2
#define RETURN_BUS_ERROR	3
#define RETURN_BUS_ARBLOST	4
#define RETURN_BUS_BUSY		5


/* special address description flags for the CAN_ID */
#define CAN_EFF_FLAG 0x80000000UL /* EFF/SFF is set in the MSB */
#define CAN_RTR_FLAG 0x40000000UL /* remote transmission request */
#define CAN_ERR_FLAG 0x20000000UL /* error message frame */

/* valid bits in CAN ID for frame formats */
#define CAN_SFF_MASK 0x000007FFUL /* standard frame format (SFF) */
#define CAN_EFF_MASK 0x1FFFFFFFUL /* extended frame format (EFF) */
#define CAN_ERR_MASK 0x1FFFFFFFUL /* omit EFF, RTR, ERR flags */

#define CAN_SFF_ID_BITS     11
#define CAN_EFF_ID_BITS     29

/* CAN payload length and DLC definitions according to ISO 11898-1 */
#define CAN_MAX_DLC 8
#define CAN_MAX_DLEN 8

/*
 *  speed 16M
 */
#define MCP_16MHz_1000kBPS_CFG1 (0x00)
#define MCP_16MHz_1000kBPS_CFG2 (0xD0)
#define MCP_16MHz_1000kBPS_CFG3 (0x82)

#define MCP_16MHz_500kBPS_CFG1 (0x00)//(0x00)//(0x00)//0x00
#define MCP_16MHz_500kBPS_CFG2 (0xB5)//(0xA7)//(0xAE)//(0xBC)//0xB5
#define MCP_16MHz_500kBPS_CFG3 (0x01)//(0x01)//0x01//0x01

#define MCP_16MHz_250kBPS_CFG1 (0x01)//(0x41)
#define MCP_16MHz_250kBPS_CFG2 (0xB5)//(0xF1)
#define MCP_16MHz_250kBPS_CFG3 (0x01)//(0x85)

#define MCP_16MHz_200kBPS_CFG1 (0x01)
#define MCP_16MHz_200kBPS_CFG2 (0xFA)
#define MCP_16MHz_200kBPS_CFG3 (0x87)

#define MCP_16MHz_125kBPS_CFG1 (0x03)
#define MCP_16MHz_125kBPS_CFG2 (0xF0)
#define MCP_16MHz_125kBPS_CFG3 (0x86)

#define MCP_16MHz_100kBPS_CFG1 (0x03)
#define MCP_16MHz_100kBPS_CFG2 (0xFA)
#define MCP_16MHz_100kBPS_CFG3 (0x87)

#define MCP_16MHz_80kBPS_CFG1 (0x03)
#define MCP_16MHz_80kBPS_CFG2 (0xFF)
#define MCP_16MHz_80kBPS_CFG3 (0x87)

#define MCP_16MHz_83k3BPS_CFG1 (0x03)
#define MCP_16MHz_83k3BPS_CFG2 (0xBE)
#define MCP_16MHz_83k3BPS_CFG3 (0x07)

#define MCP_16MHz_50kBPS_CFG1 (0x07)
#define MCP_16MHz_50kBPS_CFG2 (0xFA)
#define MCP_16MHz_50kBPS_CFG3 (0x87)

#define MCP_16MHz_40kBPS_CFG1 (0x07)
#define MCP_16MHz_40kBPS_CFG2 (0xFF)
#define MCP_16MHz_40kBPS_CFG3 (0x87)

#define MCP_16MHz_33k3BPS_CFG1 (0x4E)
#define MCP_16MHz_33k3BPS_CFG2 (0xF1)
#define MCP_16MHz_33k3BPS_CFG3 (0x85)

#define MCP_16MHz_20kBPS_CFG1 (0x0F)
#define MCP_16MHz_20kBPS_CFG2 (0xFF)
#define MCP_16MHz_20kBPS_CFG3 (0x87)

#define MCP_16MHz_10kBPS_CFG1 (0x1F)
#define MCP_16MHz_10kBPS_CFG2 (0xFF)
#define MCP_16MHz_10kBPS_CFG3 (0x87)

#define MCP_16MHz_5kBPS_CFG1 (0x3F)
#define MCP_16MHz_5kBPS_CFG2 (0xFF)
#define MCP_16MHz_5kBPS_CFG3 (0x87)


#define SENSE PIN5_bm // 

#define SELECT PIN6_bm // Select the CAN Transceiver


typedef unsigned char __u8;
typedef unsigned short __u16;
typedef unsigned long __u32;
typedef __u32 canid_t;

void clientSelect(void);
void clientDeselect(void);
uint8_t SPI0_exchangeData(uint8_t data);
void SPI0TX_init(void);
void SPI0RX_init(void);
volatile uint8_t receiveData = 0;
volatile uint8_t writeData = 0;



#define ADS122C04_ADDR      0x80

// The maximum time we will wait for DRDY to go valid for a single conversion
#define ADS122C04_CONVERSION_TIMEOUT 75

// Define 2/3/4-Wire, Temperature and Raw modes
#define ADS122C04_4WIRE_MODE         0x0
#define ADS122C04_3WIRE_MODE         0x1
#define ADS122C04_2WIRE_MODE         0x2
#define ADS122C04_TEMPERATURE_MODE   0x3
#define ADS122C04_RAW_MODE           0x4
#define ADS122C04_4WIRE_HI_TEMP      0x5
#define ADS122C04_3WIRE_HI_TEMP      0x6
#define ADS122C04_2WIRE_HI_TEMP      0x7

// ADS122C04 Table 16 in Datasheet
#define ADS122C04_RESET_CMD          0x06     //0000 011x      Reset
#define ADS122C04_START_CMD          0x08     //0000 100x      Start/Sync
#define ADS122C04_POWERDOWN_CMD      0x02     //0000 001x      PowerDown
#define ADS122C04_RDATA_CMD          0x10     //0001 xxxx      RDATA
#define ADS122C04_RREG_CMD           0x20     //0010 rrxx      Read REG rr= register address 00 to 11
#define ADS122C04_WREG_CMD           0x40     //0100 rrxx      Write REG rr= register address 00 to 11

#define ADS122C04_WRITE_CMD(reg)     (ADS122C04_WREG_CMD | (reg << 2))    //Shift is 2-bit in ADS122C04
#define ADS122C04_READ_CMD(reg)      (ADS122C04_RREG_CMD | (reg << 2))    //Shift is 2-bit in ADS122C04

// ADS122C04 Table 16 in Datasheet
#define ADS122C04_CONFIG_0_REG      0 // Configuration Register 0
#define ADS122C04_CONFIG_1_REG      1 // Configuration Register 1
#define ADS122C04_CONFIG_2_REG      2 // Configuration Register 2
#define ADS122C04_CONFIG_3_REG      3 // Configuration Register 3

// Input Multiplexer Configuration
#define ADS122C04_MUX_AIN0_AIN1     0x0
#define ADS122C04_MUX_AIN0_AIN2     0x1
#define ADS122C04_MUX_AIN0_AIN3     0x2
#define ADS122C04_MUX_AIN1_AIN0     0x3
#define ADS122C04_MUX_AIN1_AIN2     0x4
#define ADS122C04_MUX_AIN1_AIN3     0x5
#define ADS122C04_MUX_AIN2_AIN3     0x6
#define ADS122C04_MUX_AIN3_AIN2     0x7
#define ADS122C04_MUX_AIN0_AVSS     0x8
#define ADS122C04_MUX_AIN1_AVSS     0x9
#define ADS122C04_MUX_AIN2_AVSS     0xa
#define ADS122C04_MUX_AIN3_AVSS     0xb
#define ADS122C04_MUX_REFPmREFN     0xc
#define ADS122C04_MUX_AVDDmAVSS     0xd
#define ADS122C04_MUX_SHORTED       0xe

// Gain Configuration
#define ADS122C04_GAIN_1            0x0
#define ADS122C04_GAIN_2            0x1
#define ADS122C04_GAIN_4            0x2
#define ADS122C04_GAIN_8            0x3
#define ADS122C04_GAIN_16           0x4
#define ADS122C04_GAIN_32           0x5
#define ADS122C04_GAIN_64           0x6
#define ADS122C04_GAIN_128          0x7

// PGA Bypass (PGA is disabled when the PGA_BYPASS bit is set)
#define ADS122C04_PGA_DISABLED      0x1
#define ADS122C04_PGA_ENABLED       0x0
#define ADS122C04_DATA_RATE_20SPS   0x0
#define ADS122C04_DATA_RATE_45SPS   0x1
#define ADS122C04_DATA_RATE_90SPS   0x2
#define ADS122C04_DATA_RATE_175SPS  0x3
#define ADS122C04_DATA_RATE_330SPS  0x4
#define ADS122C04_DATA_RATE_600SPS  0x5
#define ADS122C04_DATA_RATE_1000SPS 0x6

// Operating Mode
#define ADS122C04_OP_MODE_NORMAL    0x0
#define ADS122C04_OP_MODE_TURBO     0x1

// Conversion Mode
#define ADS122C04_CONVERSION_MODE_SINGLE_SHOT   0x0
#define ADS122C04_CONVERSION_MODE_CONTINUOUS    0x1

// Voltage Reference Selection
#define ADS122C04_VREF_INTERNAL            0x0 //2.048V internal
#define ADS122C04_VREF_EXT_REF_PINS        (0x1) //REFp and REFn external
#define ADS122C04_VREF_AVDD                0x2 //Analog Supply AVDD and AVSS

// Temperature Sensor Mode
#define ADS122C04_TEMP_SENSOR_OFF          0x0
#define ADS122C04_TEMP_SENSOR_ON           0x1

// Data Counter Enable
#define ADS122C04_DCNT_DISABLE             0x0
#define ADS122C04_DCNT_ENABLE              0x1

// Data Integrity Check Enable
#define ADS122C04_CRC_DISABLED             0x0
#define ADS122C04_CRC_INVERTED             0x1
#define ADS122C04_CRC_CRC16_ENABLED        0x2

// Burn-Out Current Source
#define ADS122C04_BURN_OUT_CURRENT_OFF     0x0
#define ADS122C04_BURN_OUT_CURRENT_ON      0x1

// IDAC Current Setting
#define ADS122C04_IDAC_CURRENT_OFF         0x0
#define ADS122C04_IDAC_CURRENT_10_UA       0x1
#define ADS122C04_IDAC_CURRENT_50_UA       0x2
#define ADS122C04_IDAC_CURRENT_100_UA      0x3
#define ADS122C04_IDAC_CURRENT_250_UA      0x4
#define ADS122C04_IDAC_CURRENT_500_UA      0x5
#define ADS122C04_IDAC_CURRENT_1000_UA     0x6
#define ADS122C04_IDAC_CURRENT_1500_UA     0x7

#define ADS122C04_IDAC1_DISABLED           0x0
#define ADS122C04_IDAC1_AIN0               0x1
#define ADS122C04_IDAC1_AIN1               0x2
#define ADS122C04_IDAC1_AIN2               0x3
#define ADS122C04_IDAC1_AIN3               0x4
#define ADS122C04_IDAC1_REFP               0x5
#define ADS122C04_IDAC1_REFN               0x6

// IDAC2 Routing Configuration
#define ADS122C04_IDAC2_DISABLED           0x0
#define ADS122C04_IDAC2_AIN0               0x1
#define ADS122C04_IDAC2_AIN1               0x2
#define ADS122C04_IDAC2_AIN2               0x3
#define ADS122C04_IDAC2_AIN3               0x4
#define ADS122C04_IDAC2_REFP               0x5
#define ADS122C04_IDAC2_REFN               0x6


#define DAC8571_ADDR                0x9C // 1001 1A00 A is connected to pin high 5.0V
//  ERROR CODES
#define DAC8571_OK                  0x00
#define DAC8571_I2C_ERROR           0x81
#define DAC8571_ADDRESS_ERROR       0x82
#define DAC8571_BUFFER_ERROR        0x83

//  WRITE MODE
#define DAC8571_MODE_STORE_CACHE    0x00
#define DAC8571_MODE_NORMAL         0x01
#define DAC8571_MODE_WRITE_CACHE    0x02

//  DAC VALUES (percentages)
#define DAC8571_VALUE_00            0x0000
#define DAC8571_VALUE_25            0x4000
#define DAC8571_VALUE_50            0x8000
#define DAC8571_VALUE_75            0xC000
#define DAC8571_VALUE_100           0xFFFF


//  POWER DOWN MODE
#define DAC8571_PD_LOW_POWER        0x00
#define DAC8571_PD_FAST             0x01
#define DAC8571_PD_1_KOHM           0x02
#define DAC8571_PD_100_KOHM         0x03
#define DAC8571_PD_HI_Z             0x04

#define ADC_RESET PIN7_bm // PB5

unsigned char canbustxcrc[13]={0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00};
unsigned int calset_value[15]={0,0,0,0,0,0,0,0,0,0};
long long caladc_count[15]={0,0,0,0,0,0,0,0,0,0};
char output_sign[15]={'+','+','+','+','+','+','+','+','+','+',};
unsigned char company[150]={' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' '};	


float cal_factor;
//double cal_factor;

double snsr_avg_data[50];
double temp_trend_data[50];

double Digital_Filter_Value,delta_value,temp_delta_value,H2_delta_smooth,H2_delta_smooth_sleep,Temp_H2_delta_smooth_compare,H2C,Temp_Ramp_Down,Temp_Ramp_Up,Temp_Down_Factor,Temp_Up_Factor,N2_delta_smooth,N2C,H2_min,N2_max,prev_H2_min,prev_N2_max,Prev_Net_cumu_change,Final_Cal_value,H2_min_cumulative,N2_max_cumulative,Net_cumu_change,comp_value;

double current_factor;
double T_Std_Dev,Raw_Snsr_Mv,Raw_Delta_Mv,Avg_adc_data_Mv;
unsigned char sd_stability_flag,poloc,overrange;
unsigned char Samp_Interval,rxcntr,strt,factory_mode,cal_point,sesson_end,H2_Pull_Value,Avg_adjust_by;
long long span_value,zero_value,Low_Alarm,High_Alarm;	
long long disp_value,h2out;	
unsigned int H2_Sensor_Current,Sensor_Current,H2_current_duration,Sleep_time_count,Current_Sleep_time,Pre_Sleep_Time,no_sample,median_sample,Run_Sleep_time;
unsigned char adc_op_mode,cycle_counter,temp_cycle_counter,Array_length,Temp_status,Ignition_On_Status,Ignition_off_cycle,Sensor_Status_Flag,Low_Alarm_Flag,Hi_Alarm_Flag,Sensor_Status_Byte,txcounter,CRC_Counter_Byte;

struct can_frame {
	canid_t can_id;  /* 32 bit CAN_ID + EFF/RTR/ERR flags */
	__u8    can_dlc; /* frame payload length in byte (0 .. CAN_MAX_DLEN) */
	__u8    data[CAN_MAX_DLEN] __attribute__((aligned(8)));
};



enum CAN_CLOCK {
	MCP_20MHZ,
	MCP_16MHZ,
	MCP_8MHZ
};

enum CAN_SPEED {
	CAN_5KBPS,
	CAN_10KBPS,
	CAN_20KBPS,
	CAN_31K25BPS,
	CAN_33KBPS,
	CAN_40KBPS,
	CAN_50KBPS,
	CAN_80KBPS,
	CAN_83K3BPS,
	CAN_95KBPS,
	CAN_100KBPS,
	CAN_125KBPS,
	CAN_200KBPS,
	CAN_250KBPS,
	CAN_500KBPS,
	CAN_1000KBPS
};

enum CAN_CLKOUT {
	CLKOUT_DISABLE = -1,
	CLKOUT_DIV1 = 0x0,
	CLKOUT_DIV2 = 0x1,
	CLKOUT_DIV4 = 0x2,
	CLKOUT_DIV8 = 0x3,
};

class MCP2515
{
	public:
	enum ERROR {
		ERROR_OK        = 0,
		ERROR_FAIL      = 1,
		ERROR_ALLTXBUSY = 2,
		ERROR_FAILINIT  = 3,
		ERROR_FAILTX    = 4,
		ERROR_NOMSG     = 5
	};

	enum MASK {
		MASK0,
		MASK1
	};

	enum RXF {
		RXF0 = 0,
		RXF1 = 1,
		RXF2 = 2,
		RXF3 = 3,
		RXF4 = 4,
		RXF5 = 5
	};

	enum RXBn {
		RXB0 = 0,
		RXB1 = 1
	};

	enum TXBn {
		TXB0 = 0,
		TXB1 = 1,
		TXB2 = 2
	};

//	enum /*class*/ CANINTF : uint8_t {
	enum /*class*/ CANINTF  {
		CANINTF_RX0IF = 0x01,
		CANINTF_RX1IF = 0x02,
		CANINTF_TX0IF = 0x04,
		CANINTF_TX1IF = 0x08,
		CANINTF_TX2IF = 0x10,
		CANINTF_ERRIF = 0x20,
		CANINTF_WAKIF = 0x40,
		CANINTF_MERRF = 0x80
	};

//	enum /*class*/ EFLG : uint8_t {
	enum /*class*/ EFLG {
		EFLG_RX1OVR = (1<<7),
		EFLG_RX0OVR = (1<<6),
		EFLG_TXBO   = (1<<5),
		EFLG_TXEP   = (1<<4),
		EFLG_RXEP   = (1<<3),
		EFLG_TXWAR  = (1<<2),
		EFLG_RXWAR  = (1<<1),
		EFLG_EWARN  = (1<<0)
	};

	private:
	static const uint8_t CANCTRL_REQOP = 0xE0;
	static const uint8_t CANCTRL_ABAT = 0x10;
	static const uint8_t CANCTRL_OSM = 0x08;
	static const uint8_t CANCTRL_CLKEN = 0x04;
	static const uint8_t CANCTRL_CLKPRE = 0x03;

	//enum /*class*/ CANCTRL_REQOP_MODE : uint8_t {
	enum /*class*/ CANCTRL_REQOP_MODE {
		CANCTRL_REQOP_NORMAL     = 0x00,
		CANCTRL_REQOP_SLEEP      = 0x20,
		CANCTRL_REQOP_LOOPBACK   = 0x40,
		CANCTRL_REQOP_LISTENONLY = 0x60,
		CANCTRL_REQOP_CONFIG     = 0x80,
		CANCTRL_REQOP_POWERUP    = 0xE0
	};

	static const uint8_t CANSTAT_OPMOD = 0xE0;
	static const uint8_t CANSTAT_ICOD = 0x0E;

	static const uint8_t CNF3_SOF = 0x80;

	static const uint8_t TXB_EXIDE_MASK = 0x08;
	static const uint8_t DLC_MASK       = 0x0F;
	static const uint8_t RTR_MASK       = 0x40;

	static const uint8_t RXBnCTRL_RXM_STD    = 0x20;
	static const uint8_t RXBnCTRL_RXM_EXT    = 0x40;
	static const uint8_t RXBnCTRL_RXM_STDEXT = 0x00;
	static const uint8_t RXBnCTRL_RXM_MASK   = 0x60;
	static const uint8_t RXBnCTRL_RTR        = 0x08;
	static const uint8_t RXB0CTRL_BUKT       = 0x04;
	static const uint8_t RXB0CTRL_FILHIT_MASK = 0x03;
	static const uint8_t RXB1CTRL_FILHIT_MASK = 0x07;
	static const uint8_t RXB0CTRL_FILHIT = 0x00;
	static const uint8_t RXB1CTRL_FILHIT = 0x01;

	static const uint8_t MCP_SIDH = 0;
	static const uint8_t MCP_SIDL = 1;
	static const uint8_t MCP_EID8 = 2;
	static const uint8_t MCP_EID0 = 3;
	static const uint8_t MCP_DLC  = 4;
	static const uint8_t MCP_DATA = 5;

//	enum /*class*/ STAT : uint8_t {
	enum /*class*/ STAT  {
		STAT_RX0IF = (1<<0),
		STAT_RX1IF = (1<<1)
	};

	static const uint8_t STAT_RXIF_MASK = STAT_RX0IF | STAT_RX1IF;

//	enum /*class*/ TXBnCTRL : uint8_t {
	enum /*class*/ TXBnCTRL {
		TXB_ABTF   = 0x40,
		TXB_MLOA   = 0x20,
		TXB_TXERR  = 0x10,
		TXB_TXREQ  = 0x08,
		TXB_TXIE   = 0x04,
		TXB_TXP    = 0x03
	};

	static const uint8_t EFLG_ERRORMASK = EFLG_RX1OVR
	| EFLG_RX0OVR
	| EFLG_TXBO
	| EFLG_TXEP
	| EFLG_RXEP;

//	enum /*class*/ INSTRUCTION : uint8_t {
	enum /*class*/ INSTRUCTION  {
		INSTRUCTION_WRITE       = 0x02,
		INSTRUCTION_READ        = 0x03,
		INSTRUCTION_BITMOD      = 0x05,
		INSTRUCTION_LOAD_TX0    = 0x40,
		INSTRUCTION_LOAD_TX1    = 0x42,
		INSTRUCTION_LOAD_TX2    = 0x44,
		INSTRUCTION_RTS_TX0     = 0x81,
		INSTRUCTION_RTS_TX1     = 0x82,
		INSTRUCTION_RTS_TX2     = 0x84,
		INSTRUCTION_RTS_ALL     = 0x87,
		INSTRUCTION_READ_RX0    = 0x90,
		INSTRUCTION_READ_RX1    = 0x94,
		INSTRUCTION_READ_STATUS = 0xA0,
		INSTRUCTION_RX_STATUS   = 0xB0,
		INSTRUCTION_RESET       = 0xC0
	};

//	enum /*class*/ REGISTER : uint8_t {
	enum /*class*/ REGISTER {
		MCP_RXF0SIDH = 0x00,
		MCP_RXF0SIDL = 0x01,
		MCP_RXF0EID8 = 0x02,
		MCP_RXF0EID0 = 0x03,
		MCP_RXF1SIDH = 0x04,
		MCP_RXF1SIDL = 0x05,
		MCP_RXF1EID8 = 0x06,
		MCP_RXF1EID0 = 0x07,
		MCP_RXF2SIDH = 0x08,
		MCP_RXF2SIDL = 0x09,
		MCP_RXF2EID8 = 0x0A,
		MCP_RXF2EID0 = 0x0B,
		MCP_CANSTAT  = 0x0E,
		MCP_CANCTRL  = 0x0F,
		MCP_RXF3SIDH = 0x10,
		MCP_RXF3SIDL = 0x11,
		MCP_RXF3EID8 = 0x12,
		MCP_RXF3EID0 = 0x13,
		MCP_RXF4SIDH = 0x14,
		MCP_RXF4SIDL = 0x15,
		MCP_RXF4EID8 = 0x16,
		MCP_RXF4EID0 = 0x17,
		MCP_RXF5SIDH = 0x18,
		MCP_RXF5SIDL = 0x19,
		MCP_RXF5EID8 = 0x1A,
		MCP_RXF5EID0 = 0x1B,
		MCP_TEC      = 0x1C,
		MCP_REC      = 0x1D,
		MCP_RXM0SIDH = 0x20,
		MCP_RXM0SIDL = 0x21,
		MCP_RXM0EID8 = 0x22,
		MCP_RXM0EID0 = 0x23,
		MCP_RXM1SIDH = 0x24,
		MCP_RXM1SIDL = 0x25,
		MCP_RXM1EID8 = 0x26,
		MCP_RXM1EID0 = 0x27,
		MCP_CNF3     = 0x28,
		MCP_CNF2     = 0x29,
		MCP_CNF1     = 0x2A,
		MCP_CANINTE  = 0x2B,
		MCP_CANINTF  = 0x2C,
		MCP_EFLG     = 0x2D,
		MCP_TXB0CTRL = 0x30,
		MCP_TXB0SIDH = 0x31,
		MCP_TXB0SIDL = 0x32,
		MCP_TXB0EID8 = 0x33,
		MCP_TXB0EID0 = 0x34,
		MCP_TXB0DLC  = 0x35,
		MCP_TXB0DATA = 0x36,
		MCP_TXB1CTRL = 0x40,
		MCP_TXB1SIDH = 0x41,
		MCP_TXB1SIDL = 0x42,
		MCP_TXB1EID8 = 0x43,
		MCP_TXB1EID0 = 0x44,
		MCP_TXB1DLC  = 0x45,
		MCP_TXB1DATA = 0x46,
		MCP_TXB2CTRL = 0x50,
		MCP_TXB2SIDH = 0x51,
		MCP_TXB2SIDL = 0x52,
		MCP_TXB2EID8 = 0x53,
		MCP_TXB2EID0 = 0x54,
		MCP_TXB2DLC  = 0x55,
		MCP_TXB2DATA = 0x56,
		MCP_RXB0CTRL = 0x60,
		MCP_RXB0SIDH = 0x61,
		MCP_RXB0SIDL = 0x62,
		MCP_RXB0EID8 = 0x63,
		MCP_RXB0EID0 = 0x64,
		MCP_RXB0DLC  = 0x65,
		MCP_RXB0DATA = 0x66,
		MCP_RXB1CTRL = 0x70,
		MCP_RXB1SIDH = 0x71,
		MCP_RXB1SIDL = 0x72,
		MCP_RXB1EID8 = 0x73,
		MCP_RXB1EID0 = 0x74,
		MCP_RXB1DLC  = 0x75,
		MCP_RXB1DATA = 0x76
	};

	//static const uint32_t DEFAULT_SPI_CLOCK = 10000000; // 10MHz
	//static const uint32_t DEFAULT_SPI_CLOCK = 3333333; // 3.3MHz
	static const uint32_t DEFAULT_SPI_CLOCK = 416666; // 416KHz

	static const int N_TXBUFFERS = 3;
	static const int N_RXBUFFERS = 2;

	static const struct TXBn_REGS {
		REGISTER CTRL;
		REGISTER SIDH;
		REGISTER DATA;
	} TXB[N_TXBUFFERS];

	static const struct RXBn_REGS {
		REGISTER CTRL;
		REGISTER SIDH;
		REGISTER DATA;
		CANINTF  CANINTF_RXnIF;
	} RXB[N_RXBUFFERS];

	uint8_t SPICS;
	uint32_t SPI_CLOCK;

	private:

	void startSPI();
	void endSPI();

	ERROR setMode(const CANCTRL_REQOP_MODE mode);

	uint8_t readRegister(const REGISTER reg);
	void readRegisters(const REGISTER reg, uint8_t values[], const uint8_t n);
	void setRegister(const REGISTER reg, const uint8_t value);
	void setRegisters(const REGISTER reg, const uint8_t values[], const uint8_t n);
	void modifyRegister(const REGISTER reg, const uint8_t mask, const uint8_t data);

	void prepareId(uint8_t *buffer, const bool ext, const uint32_t id);
	
	public:
	MCP2515(const uint8_t _CS, const uint32_t _SPI_CLOCK = DEFAULT_SPI_CLOCK);
	ERROR reset(void);
	ERROR setConfigMode();
	ERROR setListenOnlyMode();
	ERROR setSleepMode();
	ERROR setPowerupMode();
	ERROR setLoopbackMode();
	ERROR setNormalMode();
	ERROR setClkOut(const CAN_CLKOUT divisor);
	ERROR setBitrate(const CAN_SPEED canSpeed);
	ERROR setBitrate(const CAN_SPEED canSpeed, const CAN_CLOCK canClock);
	ERROR setFilterMask(const MASK num, const bool ext, const uint32_t ulData);
	ERROR setFilter(const RXF num, const bool ext, const uint32_t ulData);
	ERROR sendMessage(const TXBn txbn, const struct can_frame *frame);
	ERROR sendMessage(const struct can_frame *frame);
	ERROR readMessage(const RXBn rxbn, struct can_frame *frame);
	ERROR readMessage(struct can_frame *frame);
	bool checkReceive(void);
	bool checkError(void);
	uint8_t getErrorFlags(void);
	void clearRXnOVRFlags(void);
	uint8_t getInterrupts(void);
	uint8_t getInterruptMask(void);
	void clearInterrupts(void);
	void clearTXInterrupts(void);
	uint8_t getStatus(void);
	void clearRXnOVR(void);
	void clearMERR();
	void clearERRIF();
	uint8_t errorCountRX(void);
	uint8_t errorCountTX(void);
};

const struct MCP2515::TXBn_REGS MCP2515::TXB[MCP2515::N_TXBUFFERS] = {
	{MCP_TXB0CTRL, MCP_TXB0SIDH, MCP_TXB0DATA},
	{MCP_TXB1CTRL, MCP_TXB1SIDH, MCP_TXB1DATA},
	{MCP_TXB2CTRL, MCP_TXB2SIDH, MCP_TXB2DATA}
};
const struct MCP2515::RXBn_REGS MCP2515::RXB[N_RXBUFFERS] = {
	{MCP_RXB0CTRL, MCP_RXB0SIDH, MCP_RXB0DATA, CANINTF_RX0IF},
	{MCP_RXB1CTRL, MCP_RXB1SIDH, MCP_RXB1DATA, CANINTF_RX1IF}
};
MCP2515::MCP2515(const uint8_t _CS, const uint32_t _SPI_CLOCK)
{
	//SPI.begin();
    startSPI(); 
	//SPICS = _CS;
	//SPI_CLOCK = _SPI_CLOCK;
	//pinMode(SPICS, OUTPUT);
	//endSPI();
}
void MCP2515::startSPI() 
{
//	SPI.beginTransaction(SPISettings(SPI_CLOCK, MSBFIRST, SPI_MODE0));
//	digitalWrite(SPICS, LOW);
	SPI0TX_init();
	clientSelect();
}

void MCP2515::endSPI() 
{
	//digitalWrite(SPICS, HIGH);
	//SPI.endTransaction();
	clientDeselect();
}

void MCP2515::setRegister(const REGISTER reg, const uint8_t value)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_WRITE);
	SPI0_exchangeData(reg);
	SPI0_exchangeData(value);
	endSPI();
}

void MCP2515::setRegisters(const REGISTER reg, const uint8_t values[], const uint8_t n)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_WRITE);
	SPI0_exchangeData(reg);
	for (uint8_t i=0; i<n; i++)
	 {
		SPI0_exchangeData(values[i]);
		//_delay_ms(5);// just for testing
	}
	endSPI();
}
void MCP2515::modifyRegister(const REGISTER reg, const uint8_t mask, const uint8_t data)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_BITMOD);
	SPI0_exchangeData(reg);
	SPI0_exchangeData(mask);
	SPI0_exchangeData(data);
	endSPI();
}
uint8_t MCP2515::getStatus(void)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_READ_STATUS);
	uint8_t i = SPI0_exchangeData(0x00);
	endSPI();

	return i;
}

uint8_t MCP2515::readRegister(const REGISTER reg)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_READ);
	SPI0_exchangeData(reg);
	uint8_t ret = SPI0_exchangeData(0x00);
	endSPI();

	return ret;
	
}

void MCP2515::readRegisters(const REGISTER reg, uint8_t values[], const uint8_t n)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_READ);
	SPI0_exchangeData(reg);
	// mcp2515 has auto-increment of address-pointer
	for (uint8_t i=0; i<n; i++) 
	{
		values[i] = SPI0_exchangeData(0x00);
	}
	endSPI();
}
MCP2515::ERROR MCP2515::setMode(const CANCTRL_REQOP_MODE mode)
{
	modifyRegister(MCP_CANCTRL, CANCTRL_REQOP, mode);

	/*unsigned long endTime = millis() + 10;
	bool modeMatch = false;
	while (millis() < endTime)*/
	unsigned long endTime = 100;
	unsigned char millsec=0;
	bool modeMatch = false;
	while (millsec < endTime)
	 {
		uint8_t newmode = readRegister(MCP_CANSTAT);
		newmode &= CANSTAT_OPMOD;

		modeMatch = newmode == mode;

		if (modeMatch)
		 {
			break;
		}
		_delay_ms(1);
		millsec=millsec+1;
	}

	return modeMatch ? ERROR_OK : ERROR_FAIL;

}


MCP2515::ERROR MCP2515::setConfigMode()
{
	return setMode(CANCTRL_REQOP_CONFIG);
}

MCP2515::ERROR MCP2515::setListenOnlyMode()
{
	return setMode(CANCTRL_REQOP_LISTENONLY);
}

MCP2515::ERROR MCP2515::setSleepMode()
{
	return setMode(CANCTRL_REQOP_SLEEP);
}

MCP2515::ERROR MCP2515::setLoopbackMode()
{
	return setMode(CANCTRL_REQOP_LOOPBACK);
}

MCP2515::ERROR MCP2515::setNormalMode()
{
	return setMode(CANCTRL_REQOP_NORMAL);
}

MCP2515::ERROR MCP2515::setPowerupMode()
{
	return setMode(CANCTRL_REQOP_POWERUP);
}

MCP2515::ERROR MCP2515::setBitrate(const CAN_SPEED canSpeed)
{
	return setBitrate(canSpeed, MCP_16MHZ);
	//return setBitrate(canSpeed, MCP_8MHZ);
}
MCP2515::ERROR MCP2515::setBitrate(const CAN_SPEED canSpeed, CAN_CLOCK canClock)
{
	ERROR error = setConfigMode();
	if (error != ERROR_OK)
	 {
		return error;
	}

	uint8_t set, cfg1, cfg2, cfg3;
	set = 1;
	switch (canClock)
	{
		case (MCP_16MHZ):
		switch (canSpeed)
		{
			case (CAN_250KBPS):                                             // 250Kbps
			cfg1 = MCP_16MHz_250kBPS_CFG1;
			cfg2 = MCP_16MHz_250kBPS_CFG2;
			cfg3 = MCP_16MHz_250kBPS_CFG3;
			break;

			case (CAN_500KBPS):                                             // 500Kbps
			cfg1 = MCP_16MHz_500kBPS_CFG1;
			cfg2 = MCP_16MHz_500kBPS_CFG2;
			cfg3 = MCP_16MHz_500kBPS_CFG3;
			break;

			case (CAN_1000KBPS):                                            //   1Mbps
			cfg1 = MCP_16MHz_1000kBPS_CFG1;
			cfg2 = MCP_16MHz_1000kBPS_CFG2;
			cfg3 = MCP_16MHz_1000kBPS_CFG3;
			break;

			default:
			set = 0;
			break;
		}
		break;

      default:
      set = 0;
      break;
      }

      if (set)
	   {
	      setRegister(MCP_CNF1, cfg1);
	      setRegister(MCP_CNF2, cfg2);
	      setRegister(MCP_CNF3, cfg3);
	      return ERROR_OK;
      }
      else
	   {
	      return ERROR_FAIL;
      }
}


MCP2515::ERROR MCP2515::setClkOut(const CAN_CLKOUT divisor)
{
	if (divisor == CLKOUT_DISABLE) {
		/* Turn off CLKEN */
		modifyRegister(MCP_CANCTRL, CANCTRL_CLKEN, 0x00);

		/* Turn on CLKOUT for SOF */
		modifyRegister(MCP_CNF3, CNF3_SOF, CNF3_SOF);
		return ERROR_OK;
	}

	/* Set the prescaler (CLKPRE) */
	modifyRegister(MCP_CANCTRL, CANCTRL_CLKPRE, divisor);

	/* Turn on CLKEN */
	modifyRegister(MCP_CANCTRL, CANCTRL_CLKEN, CANCTRL_CLKEN);

	/* Turn off CLKOUT for SOF */
	modifyRegister(MCP_CNF3, CNF3_SOF, 0x00);
	return ERROR_OK;
}

void MCP2515::prepareId(uint8_t *buffer, const bool ext, const uint32_t id)
{
	uint16_t canid = (uint16_t)(id & 0x0FFFF);

	if (ext) {
		buffer[MCP_EID0] = (uint8_t) (canid & 0xFF);
		buffer[MCP_EID8] = (uint8_t) (canid >> 8);
		canid = (uint16_t)(id >> 16);
		buffer[MCP_SIDL] = (uint8_t) (canid & 0x03);
		buffer[MCP_SIDL] += (uint8_t) ((canid & 0x1C) << 3);
		buffer[MCP_SIDL] |= TXB_EXIDE_MASK;
		buffer[MCP_SIDH] = (uint8_t) (canid >> 5);
		} else {
		buffer[MCP_SIDH] = (uint8_t) (canid >> 3);
		buffer[MCP_SIDL] = (uint8_t) ((canid & 0x07 ) << 5);
		buffer[MCP_EID0] = 0;
		buffer[MCP_EID8] = 0;
	}
}
MCP2515::ERROR MCP2515::setFilterMask(const MASK mask, const bool ext, const uint32_t ulData)
{
	ERROR res = setConfigMode();
	if (res != ERROR_OK) {
		return res;
	}
	
	uint8_t tbufdata[4];
	prepareId(tbufdata, ext, ulData);

	REGISTER reg;
	switch (mask) {
		case MASK0: reg = MCP_RXM0SIDH; break;
		case MASK1: reg = MCP_RXM1SIDH; break;
		default:
		return ERROR_FAIL;
	}

	setRegisters(reg, tbufdata, 4);
	
	return ERROR_OK;
}

MCP2515::ERROR MCP2515::setFilter(const RXF num, const bool ext, const uint32_t ulData)
{
	ERROR res = setConfigMode();
	if (res != ERROR_OK)
	{
		return res;
	}

	REGISTER reg;

	switch (num) {
		case RXF0: reg = MCP_RXF0SIDH; break;
		case RXF1: reg = MCP_RXF1SIDH; break;
		case RXF2: reg = MCP_RXF2SIDH; break;
		case RXF3: reg = MCP_RXF3SIDH; break;
		case RXF4: reg = MCP_RXF4SIDH; break;
		case RXF5: reg = MCP_RXF5SIDH; break;
		default:
		return ERROR_FAIL;
	}

	uint8_t tbufdata[4];
	prepareId(tbufdata, ext, ulData);
	setRegisters(reg, tbufdata, 4);

	return ERROR_OK;
}
MCP2515::ERROR MCP2515::sendMessage(const TXBn txbn, const struct can_frame *frame)
{
	if (frame->can_dlc > CAN_MAX_DLEN) 
	{
		return ERROR_FAILTX;
	}

	const struct TXBn_REGS *txbuf = &TXB[txbn];

	uint8_t data[13];
	//uint8_t data[17];
	//uint8_t data[19];//n

	//bool ext = (frame->can_id & CAN_EFF_FLAG);// it is not working for extended frame
    bool ext = 1;// previous it was 1
	bool rtr = (frame->can_id & CAN_RTR_FLAG);
	uint32_t id = (frame->can_id & (ext ? CAN_EFF_MASK : CAN_SFF_MASK));

	prepareId(data, ext, id);

	data[MCP_DLC] = rtr ? (frame->can_dlc | RTR_MASK) : frame->can_dlc;

	memcpy(&data[MCP_DATA], frame->data, frame->can_dlc);

	setRegisters(txbuf->SIDH, data, 5 + frame->can_dlc);

	modifyRegister(txbuf->CTRL, TXB_TXREQ, TXB_TXREQ);

	uint8_t ctrl = readRegister(txbuf->CTRL);
	if ((ctrl & (TXB_ABTF | TXB_MLOA | TXB_TXERR)) != 0)
	{
		return ERROR_FAILTX;
	}
	return ERROR_OK;
}

MCP2515::ERROR MCP2515::sendMessage(const struct can_frame *frame)
{
	if (frame->can_dlc > CAN_MAX_DLEN)
	 {
		return ERROR_FAILTX;
	}

	TXBn txBuffers[N_TXBUFFERS] = {TXB0, TXB1, TXB2};

	for (int i=0; i<N_TXBUFFERS; i++)
	 {
		const struct TXBn_REGS *txbuf = &TXB[txBuffers[i]];
		uint8_t ctrlval = readRegister(txbuf->CTRL);
		if ( (ctrlval & TXB_TXREQ) == 0 )
		 {
			return sendMessage(txBuffers[i], frame);
		}
	}

	return ERROR_ALLTXBUSY;
}
MCP2515::ERROR MCP2515::readMessage(const RXBn rxbn, struct can_frame *frame)
{
	const struct RXBn_REGS *rxb = &RXB[rxbn];

	uint8_t tbufdata[5];

	readRegisters(rxb->SIDH, tbufdata, 5);

	uint32_t id = (tbufdata[MCP_SIDH]<<3) + (tbufdata[MCP_SIDL]>>5);

	if ( (tbufdata[MCP_SIDL] & TXB_EXIDE_MASK) ==  TXB_EXIDE_MASK )
	 {
		id = (id<<2) + (tbufdata[MCP_SIDL] & 0x03);
		id = (id<<8) + tbufdata[MCP_EID8];
		id = (id<<8) + tbufdata[MCP_EID0];
		id |= CAN_EFF_FLAG;

	}

	uint8_t dlc = (tbufdata[MCP_DLC] & DLC_MASK);
	if (dlc > CAN_MAX_DLEN)
	 {
		return ERROR_FAIL;
	}

	uint8_t ctrl = readRegister(rxb->CTRL);
	if (ctrl & RXBnCTRL_RTR)
	{
		id |= CAN_RTR_FLAG;
	}

	frame->can_id = id;
	frame->can_dlc = dlc;

	readRegisters(rxb->DATA, frame->data, dlc);

	modifyRegister(MCP_CANINTF, rxb->CANINTF_RXnIF, 0);

	return ERROR_OK;
}

MCP2515::ERROR MCP2515::readMessage(struct can_frame *frame)
{
	ERROR rc;
	uint8_t stat = getStatus();

	if ( stat & STAT_RX0IF )
	 {
		rc = readMessage(RXB0, frame);
		} else if ( stat & STAT_RX1IF )
		 {
		rc = readMessage(RXB1, frame);
		} else {
		rc = ERROR_NOMSG;
	}

	return rc;
}


bool MCP2515::checkReceive(void)
{
	uint8_t res = getStatus();
	if ( res & STAT_RXIF_MASK ) 
	{
		return true;
	} 
	else 
	{
		return false;
	}
}

bool MCP2515::checkError(void)
{
	uint8_t eflg = getErrorFlags();

	if ( eflg & EFLG_ERRORMASK ) {
		return true;
		} else {
		return false;
	}
}

uint8_t MCP2515::getErrorFlags(void)
{
	return readRegister(MCP_EFLG);
}

void MCP2515::clearRXnOVRFlags(void)
{
	modifyRegister(MCP_EFLG, EFLG_RX0OVR | EFLG_RX1OVR, 0);
}

uint8_t MCP2515::getInterrupts(void)
{
	return readRegister(MCP_CANINTF);
}

void MCP2515::clearInterrupts(void)
{
	setRegister(MCP_CANINTF, 0);
}

uint8_t MCP2515::getInterruptMask(void)
{
	return readRegister(MCP_CANINTE);
}

void MCP2515::clearTXInterrupts(void)
{
	modifyRegister(MCP_CANINTF, (CANINTF_TX0IF | CANINTF_TX1IF | CANINTF_TX2IF), 0);
}

void MCP2515::clearRXnOVR(void)
{
	uint8_t eflg = getErrorFlags();
	if (eflg != 0) {
		clearRXnOVRFlags();
		clearInterrupts();
		//modifyRegister(MCP_CANINTF, CANINTF_ERRIF, 0);
	}
	
}

void MCP2515::clearMERR()
{
	//modifyRegister(MCP_EFLG, EFLG_RX0OVR | EFLG_RX1OVR, 0);
	//clearInterrupts();
	modifyRegister(MCP_CANINTF, CANINTF_MERRF, 0);
}

void MCP2515::clearERRIF()
{
	//modifyRegister(MCP_EFLG, EFLG_RX0OVR | EFLG_RX1OVR, 0);
	//clearInterrupts();
	modifyRegister(MCP_CANINTF, CANINTF_ERRIF, 0);
}

uint8_t MCP2515::errorCountRX(void)
{
	return readRegister(MCP_REC);
}

uint8_t MCP2515::errorCountTX(void)
{
	return readRegister(MCP_TEC);
}

MCP2515::ERROR MCP2515::reset(void)
{
	startSPI();
	SPI0_exchangeData(INSTRUCTION_RESET);
	endSPI();

	_delay_ms(10);

	uint8_t zeros[14];
	memset(zeros, 0, sizeof(zeros));
	setRegisters(MCP_TXB0CTRL, zeros, 14);
	setRegisters(MCP_TXB1CTRL, zeros, 14);
	setRegisters(MCP_TXB2CTRL, zeros, 14);

	setRegister(MCP_RXB0CTRL, 0);
	setRegister(MCP_RXB1CTRL, 0);

	setRegister(MCP_CANINTE, CANINTF_RX0IF | CANINTF_RX1IF | CANINTF_ERRIF | CANINTF_MERRF);

	// receives all valid messages using either Standard or Extended Identifiers that
	// meet filter criteria. RXF0 is applied for RXB0, RXF1 is applied for RXB1
	modifyRegister(MCP_RXB0CTRL,
	RXBnCTRL_RXM_MASK | RXB0CTRL_BUKT | RXB0CTRL_FILHIT_MASK,
	RXBnCTRL_RXM_STDEXT | RXB0CTRL_BUKT | RXB0CTRL_FILHIT);
	modifyRegister(MCP_RXB1CTRL,
	RXBnCTRL_RXM_MASK | RXB1CTRL_FILHIT_MASK,
	RXBnCTRL_RXM_STDEXT | RXB1CTRL_FILHIT);

	// clear filters and masks
	// do not filter any standard frames for RXF0 used by RXB0
	// do not filter any extended frames for RXF1 used by RXB1
	RXF filters[] = {RXF0, RXF1, RXF2, RXF3, RXF4, RXF5};
	for (int i=0; i<6; i++) {
		bool ext = (i == 1);
		ERROR result = setFilter(filters[i], ext, 0);
		if (result != ERROR_OK) {
			return result;
		}
	}

	MASK masks[] = {MASK0, MASK1};
	for (int i=0; i<2; i++) {
		ERROR result = setFilterMask(masks[i], true, 0);
		if (result != ERROR_OK) {
			return result;
		}
	}

	return ERROR_OK;
}


void SPI0TX_init(void)
{
	PORTA.DIR |= PIN1_bm; /* Set MOSI pin direction to output */
	PORTA.DIR &= ~PIN2_bm; /* Set MISO pin direction to input */
	PORTA.DIR |= PIN3_bm; /* Set SCK pin direction to output */
	PORTA.DIR |= PIN4_bm; /* Set SS pin direction to output */
	//SPI0.CTRLA = SPI_CLK2X_bm /* Enable double-speed */
	//| SPI_DORD_bm /* LSB is transmitted first */
	//| SPI_ENABLE_bm /* Enable module */
	//| SPI_MASTER_bm /* SPI module in Host mode */
	//| SPI_PRESC_DIV16_gc; /* System Clock divided by 16 */
    SPI0.CTRLA = 1 << SPI_CLK2X_bp /* Enable double-speed */
	|0<< SPI_DORD_bp /* MSB is transmitted first */
	|1<< SPI_ENABLE_bp /* Enable module */
	|1<< SPI_MASTER_bp /* SPI module in Host mode */
	|1<< SPI_PRESC_DIV4_gc; /* System Clock divided by 16 */
	
}



void SPI0RX_init(void)
{

	PORTA.DIR &= ~PIN1_bm; /* Set MOSI pin direction to input */
	PORTA.DIR |= PIN2_bm; /* Set MISO pin direction to output */
	PORTA.DIR &= ~PIN3_bm; /* Set SCK pin direction to input */
	PORTA.DIR &= ~PIN4_bm; /* Set SS pin direction to input */
	//	SPI0.CTRLA = SPI_DORD_bm /* LSB is transmitted first */
	//	| SPI_ENABLE_bm /* Enable module */
	//	& (~SPI_MASTER_bm); /* SPI module in Client mode */

	//SPI0.CTRLA = 1 << SPI_DORD_bp /* LSB is transmitted first */
	SPI0.CTRLA = 0 << SPI_DORD_bp /* MSB is transmitted first */
	|1<< SPI_ENABLE_bp /* Enable module */
	|0<< SPI_MASTER_bp; /* SPI module in Client mode */
	SPI0.INTCTRL = SPI_IE_bm; /* SPI Interrupt enable */
	
}

ISR(SPI0_INT_vect)
{
	receiveData = SPI0.DATA;
	SPI0.DATA = writeData;
	SPI0.INTFLAGS = SPI_IF_bm; /* Clear the Interrupt flag by writing 1 */
}

uint8_t SPI0_exchangeData(uint8_t data)
{
	SPI0.DATA = data;
	while (!(SPI0.INTFLAGS & SPI_IF_bm)) /* Waits until data are exchanged*/
	{
		;
	}
	//_delay_ms(5);// just for testing
	return SPI0.DATA;
}
void clientSelect(void)
{
	PORTA.OUT &= ~PIN4_bm; // Set SS pin value to LOW
	//SPI0TX_init();
}
void clientDeselect(void)
{
	PORTA.OUT |= PIN4_bm; // Set SS pin value to HIGH
	//SPI0RX_init();
}

/*int crc_detect(unsigned char count)
{
	unsigned int crc=0xFFFF;
	unsigned char j,pos;
	for(pos=0;pos<count;pos++)
	{
		crc^=canbustxcrc[pos];
		for(j=8;j>0;j--)
		{
			if(crc & 0x0001)
			{
				crc=crc>>1;
				//crc^=0xA001;//for modbus rtu
				crc^=0x4599;//for CAN CRC
			}
			else
			{
				crc=crc>>1;
			}
		}
	}
	crc= crc & 0x7FFF; //for 15 bit crc calculation in CAN bus
	return crc;
}	*/
		
		
// Bit field type register configuration
// Configuration Map register ADS122C04
//--------------Address 0x00---------------------------------
struct CONFIG_REG_0{
	uint8_t PGA_BYPASS:1;                           // 0
	uint8_t GAIN:3;                                 // 1-3
	uint8_t MUX:4;                                  // 4-7
};
union CONFIG_REG_0_U {
	uint8_t all;
	struct CONFIG_REG_0 bit;
};

//--------------Address 0x01---------------------------------
struct CONFIG_REG_1{
	uint8_t TS:1;                                   // 0
	uint8_t VVREF:2;                                 // 1-2
	uint8_t CMBIT:1;                                // 3
	uint8_t MODE:1;                                 // 4
	uint8_t DR:3;                                   // 5-7
};
union CONFIG_REG_1_U {
	uint8_t all;
	struct CONFIG_REG_1 bit;
};

//--------------Address 0x02---------------------------------
struct CONFIG_REG_2{
	uint8_t IDAC:3;                                 // 0-2
	uint8_t BCS:1;                                  // 3
	uint8_t CRCbits:2;                              // 4-5
	uint8_t DCNT:1;                                 // 6
	uint8_t DRDY:1;                                 // 7
};
union CONFIG_REG_2_U {
	uint8_t all;
	struct CONFIG_REG_2 bit;
};

//--------------Address 0x03---------------------------------
struct CONFIG_REG_3{
	uint8_t RESERVED:2;                             // 0-1
	uint8_t I2MUX:3;                                // 2-4
	uint8_t I1MUX:3;                                // 5-7
};
union CONFIG_REG_3_U {
	uint8_t all;
	struct CONFIG_REG_3 bit;
};

// All four registers
typedef struct ADS122C04Reg{
	union CONFIG_REG_0_U reg0;
	union CONFIG_REG_1_U reg1;
	union CONFIG_REG_2_U reg2;
	union CONFIG_REG_3_U reg3;
} ADS122C04Reg_t;

// Union for the 14-bit internal Temperature
// To simplify converting from uint16_t to int16_t
// without using a cast
union internal_temperature_union{
	int16_t INT16;
	uint16_t UINT16;
};

// Union for the 24-bit raw voltage
// To simplify converting from uint32_t to int32_t
// without using a cast
union raw_voltage_union{
	int32_t INT32;
	uint32_t UINT32;
};

// struct to hold the initialization parameters
typedef struct{
	uint8_t inputMux;
	uint8_t gainLevel;
	uint8_t pgaBypass;
	uint8_t dataRate;
	uint8_t opMode;
	uint8_t convMode;
	uint8_t selectVref;
	uint8_t tempSensorEn;
	uint8_t dataCounterEn;
	uint8_t dataCRCen;
	uint8_t burnOutEn;
	uint8_t idacCurrent;
	uint8_t routeIDAC1;
	uint8_t routeIDAC2;
} ADS122C04_initParam;

/*Using default clock 3.33MHz */
void TCA0_init(void);
void PIN_init(void);
void TCA0_hardReset(void);

// Read the raw signed 24-bit ADC value as int32_t
// This uses the internal 2.048V reference with the gain set to 1
// The LSB is 2.048 / 2^23 = 0.24414 uV (0.24414 microvolts)
int32_t readRawVoltage(uint8_t rate = ADS122C04_DATA_RATE_20SPS);

// Read the raw signed 24-bit ADC value as uint32_t
// The ADC data is returned in the least-significant 24-bits
uint32_t readADC(void);

// Read the internal temperature (C)
float readInternalTemperature(uint8_t rate = ADS122C04_DATA_RATE_20SPS);

void reset(void); // Reset the ADS122C04
void start(void); // Start a conversion
void ADC_powerdown(void); // Put the chip into low power mode

 // Default to using 'safe' settings (disable the IDAC current sources)
 //void setInputMultiplexer(uint8_t mux_config = ADS122C04_MUX_AIN1_AIN0); // Configure the input multiplexer
 void setInputMultiplexer(uint8_t mux_config); // Configure the input multiplexer
 void setGain(uint8_t gain_config = ADS122C04_GAIN_1); // Configure the gain
 void enablePGA(uint8_t enable = ADS122C04_PGA_DISABLED); // Enable/disable the Programmable Gain Amplifier
 void setDataRate(uint8_t rate = ADS122C04_DATA_RATE_20SPS); // Set the data rate (sample speed)
  void setOperatingMode(uint8_t mode = ADS122C04_OP_MODE_NORMAL); // Configure the operating mode (normal / turbo)
 //void setConversionMode(uint8_t mode = ADS122C04_CONVERSION_MODE_SINGLE_SHOT); // Configure the conversion mode (single-shot / continuous)
 void setConversionMode(uint8_t mode); // Configure the conversion mode (single-shot / continuous)
 void setVoltageReference(uint8_t ref = ADS122C04_VREF_INTERNAL); // Configure the voltage reference
 void enableInternalTempSensor(uint8_t enable = ADS122C04_TEMP_SENSOR_OFF); // Enable / disable the internal temperature sensor
 void setDataCounter(uint8_t enable = ADS122C04_DCNT_DISABLE); // Enable / disable the conversion data counter
 void setDataIntegrityCheck(uint8_t setting = ADS122C04_CRC_DISABLED); // Configure the data integrity check
 void setBurnOutCurrent(uint8_t enable = ADS122C04_BURN_OUT_CURRENT_OFF); // Enable / disable the 10uA burn-out current source
 void setIDACcurrent(uint8_t current = ADS122C04_IDAC_CURRENT_OFF); // Configure the internal programmable current sources
 void setIDAC1mux(uint8_t setting = ADS122C04_IDAC1_DISABLED); // Configure the IDAC1 routing
 void setIDAC2mux(uint8_t setting = ADS122C04_IDAC2_DISABLED); // Configure the IDAC2 routing

 bool checkDataReady(void); // Check the status of the DRDY bit in Config Register 2

 uint8_t getInputMultiplexer(void); // input multiplexer configuration
 uint8_t getGain(void); // gain setting
 uint8_t getPGAstatus(void); // Programmable Gain Amplifier status
 uint8_t getDataRate(void); // data rate (sample speed)
 uint8_t getOperatingMode(void); // operating mode (normal / turbo)
 uint8_t getConversionMode(void); // conversion mode (single-shot / continuous)
 uint8_t getVoltageReference(void); // voltage reference configuration
 uint8_t getInternalTempSensorStatus(void); // internal temperature sensor status
 uint8_t getDataCounter(void); // data counter status
 uint8_t getDataIntegrityCheck(void); // data integrity check configuration
 uint8_t getBurnOutCurrent(void); // burn-out current status
 uint8_t getIDACcurrent(void); // IDAC setting
 uint8_t getIDAC1mux(void); //  IDAC1 MUX configuration
 uint8_t getIDAC2mux(void); //  IDAC2 MUX configuration


// Keep a copy of the wire mode so we can restore it after reading the internal temperature
uint8_t _wireMode = ADS122C04_RAW_MODE; //Default to using 'safe' settings (disable the IDAC current sources)
// Resistance of the reference resistor
const float PT100_REFERENCE_RESISTOR = 1620.0;

// Amplifier gain setting
// ** MAKE SURE THE CONFIG REGISTER 0 GAIN IS THE SAME AS THIS **
const float PT100_AMPLIFIER_GAIN = 8.0;
const float PT100_AMP_GAIN_HI_TEMP = 4.0;

// Internal temperature sensor resolution
// One 14-bit LSB equals 0.03125 C
const float TEMPERATURE_SENSOR_RESOLUTION = 0.03125;

ADS122C04Reg_t ADS122C04_Reg; // Global to hold copies of all four configuration registers


bool ADS122C04_init(ADS122C04_initParam *param); // initialize the ADS122C04 parameters

void ADS122C04_writeReg(uint8_t reg, uint8_t writeValue); // write a value to the selected register
bool ADS122C04_readReg(uint8_t reg, uint8_t *readValue); // read a value from the selected register (returned in readValue)

bool ADS122C04_getConversionData(uint32_t *conversionData); // read the raw 24-bit conversion result
bool ADS122C04_getConversionDataWithCount(uint32_t *conversionData, uint8_t *count); // read the raw conversion result and count (if enabled)

void ADS122C04_sendCommand(uint8_t command); // write to the selected command register
void ADS122C04_sendCommandWithValue(uint8_t command, uint8_t value); // write a value to the selected command register

bool write_on_DAC(uint16_t value);  //  returns true on success.

uint16_t DAC_read();        //  returns last successful write from device.

//       PERCENTAGE WRAPPER
void     set_DAC_Percentage(float percentage);
float    get_DAC_Percentage();

//       WRITE MODE (see defines above)
void     set_DAC_WriteMode(uint8_t mode);
uint8_t  get_DAC_WriteMode();  // 0..4  from last write (cached)

//       POWER DOWN (see defines above)
void     DAC_powerDown(uint8_t pdMode = DAC8571_PD_LOW_POWER);
void     DAC_wakeUp(uint16_t value = DAC8571_VALUE_00);

char str1[] = {"0000000    "};
char str2[] = {"0000000    "};
char str3[] = {"0000000    "};
char str4[] = {"0000000    "};	
char str5[] = {"0000000    "};	
char str6[] = {"0000000    "};	
char str7[] = {"0000000    "};	
char str8[] = {"0000000    "};		
char str9[] = {"0000000    "};
char str10[] = {"0000000    "};		
char str11[] = {"0000000    "};	
char str12[] = {"0000000    "};	
char str13[] = {"0000000    "};	
char str14[] = {"0000000    "};
char clone[]={"0000000    "};
		
char store_data[]={"               "};
	
	
unsigned char memdata,rxdata;
uint8_t  DAC_control;

bool I2C_StopMaster()
{

	TWI0.MCTRLA &= ~(TWI_ENABLE_bm);
	PORTB.DIRSET &= ~(I2C_SCL);

	return(RETURN_OK);
}

bool I2C_RawStart(uint8_t deviceAddr, uint8_t Direction)
{
	volatile uint16_t timeout;

	deviceAddr = deviceAddr | Direction; // 1 read, 0 write
	if (I2C_BUS_NOT_BUSY)
	{
		for (volatile uint16_t arbLoop = 0x04; arbLoop > 0; arbLoop--)
		{
			//TWI0.MCTRLB &= ~(1 << TWI_ACKACT_bp);
			TWI0.MADDR = deviceAddr;
			if (Direction)
			{
				// addressRead
				for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_RIF_bm) && (timeout > 0); timeout--)
				{
				}
			}
			else
			{

				// addressWrite
				for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_WIF_bm) && (timeout > 0); timeout--)
				{
				}
			}

			if (I2C_ARBLOST)
			{
				// Arbitration lost - keep retrying.
				continue;
			}

			if (I2C_BUSERR)
			{
				// Bus error - abort.
				return(RETURN_BUS_ERROR);		// RETURN_BUS_ERROR);
			}

			if (I2C_STATE_IS_LOW(TWI_RXACK_bm))
			{
				// Slave responding.
				return(RETURN_OK);		// RETURN_OK);
			}
			else
			{
				// Slave not responding - abort.
				return(RETURN_NO_SLAVE);		// RETURN_NO_SLAVE);
			}
		}
	}
	else
	{
		return(RETURN_BUS_BUSY);		// RETURN_BUS_BUSY);
	}

	return(RETURN_BUS_ARBLOST);		// RETURN_BUS_ARBLOST);
}

bool I2C_RawStop(void)
{
	volatile uint16_t timeout;

	for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_CLKHOLD_bm) && (timeout > 0); timeout--)
	{
		// Wait until we have a clock hold.
	}
	if (timeout == 0)
	{
		
		return(RETURN_FAILED);
	}

	TWI0.MCTRLB = TWI_ACKACT_NACK_gc | TWI_MCMD_STOP_gc;
	//TWI0.MCTRLB = TWI_MCMD_STOP_gc;
	for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_CLKHOLD_bm) && (timeout > 0); timeout--)
	{
		// Wait until we have a clock hold.
	}
	if (I2C_BUSERR)
	{
		
		TWI0.MSTATUS = TWI_BUSERR_bm;
	}

	return(RETURN_OK);
}


void I2C_RawForceStop(void)
{

	I2C_RawStop();
	TWI0.MSTATUS |= TWI_BUSSTATE_IDLE_gc;	//Force TWI state machine into IDLE state
	TWI0.MCTRLB |= TWI_FLUSH_bm;			// Purge MADDR and MDATA
}

bool I2C_RawWrite(uint8_t write_data)
{
	volatile uint16_t timeout;

	if (I2C_BUS_OWNER)
	{
		for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_CLKHOLD_bm) && (timeout > 0); timeout--)
		{
			// Wait until we have a clock hold.
		}
		if (timeout == 0)
		{
			// Even though we own the bus, we aren't holding the clock.
			return(RETURN_FAILED);
		}

		TWI0.MDATA = write_data;
		// while (!((TWI0.MSTATUS & TWI_WIF_bm) | (TWI0.MSTATUS & TWI_RXACK_bm))) ;		//Wait until WIF set and RXACK cleared

		for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_WIF_bm) && (timeout > 0); timeout--)
		{
		}

		if (I2C_BUSERR)
		{
			// Bus error - abort.
			return(RETURN_BUS_ERROR);		// RETURN_BUS_ERROR);
			
		}

		if (I2C_STATE_IS_LOW(TWI_RXACK_bm))
		{
			// Slave responding.
			return(RETURN_OK);		// RETURN_OK);
		}
		else
		{
			// Slave not responding - abort.
			return(RETURN_NO_SLAVE);		// RETURN_NO_SLAVE);
		}
	}

	return(RETURN_FAILED);
}



unsigned char I2C_WriteByte(uint8_t address, uint16_t reg, uint8_t data)
 {
unsigned char result=0;
unsigned int hi_addr,lo_addr;
hi_addr=reg>>8;
lo_addr=reg & 0x00FF;
	if (I2C_BUS_NOT_BUSY)
	 {
		if (I2C_RawStart(address, I2C_WRITE))
		 {
			I2C_RawStop();
			return(RETURN_FAILED);
			result=1;
		}
		
		if (I2C_RawWrite(hi_addr))
		{
			I2C_RawStop();
			return(RETURN_FAILED);
			result=1;
		}
		
		if (I2C_RawWrite(lo_addr))
		{
			I2C_RawStop();
			return(RETURN_FAILED);
			result=1;
		}


		if (I2C_RawWrite(data))
		 {
			I2C_RawStop();
			return(RETURN_FAILED);
			result=1;
		}

		I2C_RawStop();
	}
	else
	{
		return(RETURN_BUS_BUSY);		// RETURN_BUS_BUSY);
		result=1;
	}
	return(result);
}
bool I2C_RawRead(uint8_t ACK)							// ACK=1 send ACK ; ACK=0 send NACK
{
	//volatile uint8_t timeout;
	volatile uint16_t timeout;
	

	if (I2C_BUS_OWNER)
	{
		for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_CLKHOLD_bm) && (timeout > 0); timeout--)
		{
			// Wait until we have a clock hold.
		}
		if (timeout == 0)
		 {
			// Even though we own the bus, we aren't holding the clock.
			return(RETURN_FAILED);
		 }

		//TWI0.MCTRLB &= ~(1 << TWI_ACKACT_bp);
		if	(ACK == 1)
		{
			TWI0.MCTRLB &= ~(1 << TWI_ACKACT_bp);
		}		
		else
		{
			TWI0.MCTRLB |= (1 << TWI_ACKACT_bp);
		}	

		for (timeout = I2C_WAIT_TIMEOUT; I2C_STATE_IS_LOW(TWI_RIF_bm) && (timeout > 0); timeout--)
		 {
			
			
		 }
		 
		if (timeout == 0)
		 {
			// Timeout on waiting for RIF signal.
			return(RETURN_FAILED);
		 }

		//*data = TWI0.MDATA;
		memdata=TWI0.MDATA;
		/*if	(ACK == 1)
		{
			TWI0.MCTRLB &= ~(1 << TWI_ACKACT_bp);
		}		
		else			
		{
			TWI0.MCTRLB |= (1 << TWI_ACKACT_bp);	
		}	
		         */
		if (I2C_BUSERR)
		 {
			// Bus error - abort.
			return(RETURN_FAILED);		// RETURN_BUS_ERROR);
		}

		if (I2C_STATE_IS_LOW(TWI_RXACK_bm)) 
		{
			// Slave responding.
			return(RETURN_OK);		// RETURN_OK);
		} 
		else
		 {
			// Slave not responding - abort.
			return(RETURN_FAILED);		// RETURN_NO_SLAVE);
		}
	}

	return(RETURN_FAILED);
	
	
}
unsigned char I2C_ReadByte(uint8_t address, uint16_t reg)
 {
	 unsigned int hi_addr,lo_addr;
	 hi_addr=reg>>8;
	 lo_addr=reg & 0x00FF;

	if (I2C_BUS_NOT_BUSY)
	 {
		if (I2C_RawStart(address, I2C_WRITE)) 
		{
			I2C_RawStop();
			return(RETURN_FAILED);
		}

		if (I2C_RawWrite(hi_addr))
		{
			I2C_RawStop();
			return(RETURN_FAILED);
		}
		
		if (I2C_RawWrite(lo_addr))
		{
			I2C_RawStop();
			return(RETURN_FAILED);
		}
				

		if (I2C_RawStart(address, I2C_READ)) 
		{
			I2C_RawStop();
			return(RETURN_FAILED);
		}

		if (I2C_RawRead(0))
		{
			I2C_RawStop();
			return(RETURN_FAILED);
		}

		I2C_RawStop();
	}

	return(memdata);
}
unsigned char I2C_data_read(uint8_t ADDR, uint16_t location )
{
	I2C_ReadByte(ADDR, location);
	return(memdata);
}

void I2C_StartMaster()
{

	PORTB.DIRSET = I2C_SCL;
	PORTB.DIRSET = I2C_SDA;
	TWI0.CTRLA = TWI_SDAHOLD_500NS_gc | TWI_SDASETUP_8CYC_gc; // Use max SDA setup and hold times to be safe
	
	// Fast Mode Setup: 400kHz
	TWI0.MBAUD = (uint8_t)TWI0_BAUD(100000,0); /* set MBAUD register */
	
	TWI0.MCTRLA = 1 << TWI_ENABLE_bp			/* Enable TWI Master: enabled */
	| 0 << TWI_QCEN_bp					/* Quick Command Enable: disabled */
	| 0 << TWI_RIEN_bp					/* Read Interrupt Enable: disabled */
	| 1 << TWI_SMEN_bp					/* Smart Mode Enable: enabled */
	| TWI_TIMEOUT_DISABLED_gc				/* Bus Timeout Disabled */
	| 0 << TWI_WIEN_bp;					/* Write Interrupt Enable: disabled */

	TWI0.MSTATUS = TWI_BUSSTATE_IDLE_gc ;		        //Force TWI state machine into IDLE state
	TWI0.MSTATUS = (TWI_RIF_bm | TWI_WIF_bm) ;
	TWI0.MCTRLB = TWI_FLUSH_bm ;				/* Purge MADDR and MDATA */

}
void InitI2C()
{
	I2C_StartMaster();
}


bool start_transmission(char device_address)
{
	return(I2C_RawStart(device_address,I2C_WRITE));
}

bool stop_transmission()
{
	return(I2C_RawStop());
}

void write_on_bus(unsigned char ch)
{
	
	I2C_RawWrite(ch);
	
}

void ADS122C04_sendCommand(uint8_t command)
{
	start_transmission(ADS122C04_ADDR);
	write_on_bus(command);
	stop_transmission();
	
}



void start(void)
{
	ADS122C04_sendCommand(ADS122C04_START_CMD);
}

void reset(void)
{
	ADS122C04_sendCommand(ADS122C04_RESET_CMD);
}

void ADC_powerdown(void)
{
	ADS122C04_sendCommand(ADS122C04_POWERDOWN_CMD);
}


void ADS122C04_sendCommandWithValue(uint8_t command, uint8_t value)
{
	start_transmission(ADS122C04_ADDR);
	write_on_bus(command);
	write_on_bus(value);
	stop_transmission();
	
}


void ADS122C04_writeReg(uint8_t reg, uint8_t writeValue)
{
	uint8_t command = 0;
	command = ADS122C04_WRITE_CMD(reg);
	ADS122C04_sendCommandWithValue(command, writeValue);
}

bool ADS122C04_readReg(uint8_t reg, uint8_t *readValue)
{
	uint8_t command = 0;
	command = ADS122C04_READ_CMD(reg);

	start_transmission(ADS122C04_ADDR);
	write_on_bus(command);
	stop_transmission();
    if (I2C_RawStart(ADS122C04_ADDR, I2C_READ))
    {
	    I2C_RawStop();
	   
    }
	if (I2C_RawRead(1))
	{
		I2C_RawStop();
		
	}
	else
	{
		*readValue=memdata;
		I2C_RawStop();
		return(true);
	}

	return(false);
}

//Returns true if device answers on _deviceAddress
bool isConnected(void)
{
	return 0;
}


// Read the conversion result with count byte.
// The conversion result is 24-bit two's complement (signed)
// and is returned in the 24 lowest bits of the uint32_t conversionData.
// Hence it will always appear positive.
// Higher functions will need to take care of converting it to (e.g.) float or int32_t.
bool ADS122C04_getConversionDataWithCount(uint32_t *conversionData, uint8_t *count)
{
	uint8_t RXByte[4] = {0};

	start_transmission(ADS122C04_ADDR);
	write_on_bus(ADS122C04_RDATA_CMD);
	stop_transmission();

	if (I2C_RawStart(ADS122C04_ADDR, I2C_READ))
	{
		I2C_RawStop();
	}

	if (I2C_RawRead(1))
	{
		I2C_RawStop();
	}
	RXByte[0]=memdata;
	if (I2C_RawRead(1))
	{
		I2C_RawStop();
	}
	RXByte[1]=memdata;
	if (I2C_RawRead(1))
	{
		I2C_RawStop();
	}
	RXByte[2]=memdata;
	if (I2C_RawRead(1))
	{
		I2C_RawStop();
	}
	RXByte[3]=memdata;

	*count = RXByte[0];
	*conversionData = ((uint32_t)RXByte[3]) | ((uint32_t)RXByte[2]<<8) | ((uint32_t)RXByte[1]<<16);
	return(true);
}


// Read the conversion result.
bool ADS122C04_getConversionData(uint32_t *conversionData)
{
	uint8_t RXByte[3] = {0};

	
	start_transmission(ADS122C04_ADDR);
	write_on_bus(ADS122C04_RDATA_CMD);
	stop_transmission();
		if (I2C_RawStart(ADS122C04_ADDR, I2C_READ))
		{
			I2C_RawStop();
		}

		if (I2C_RawRead(1))
		{
			I2C_RawStop();
		}
		RXByte[0]=memdata;
		if (I2C_RawRead(1))
		{
			I2C_RawStop();
		}
		RXByte[1]=memdata;
		if (I2C_RawRead(1))
		{
			I2C_RawStop();
		}
		RXByte[2]=memdata;

	*conversionData = ((uint32_t)RXByte[2]) | ((uint32_t)RXByte[1]<<8) | ((uint32_t)RXByte[0]<<16);
	return(true);
}

// Read the raw signed 24-bit ADC value as uint32_t
uint32_t readADC(void)
{
	uint32_t ret_val; // The return value

	// Read the conversion result
	if(ADS122C04_getConversionData(&ret_val) == false)
	{
		return(0);
	}

	return(ret_val);
}

// Configure the input multiplexer
void setInputMultiplexer(uint8_t mux_config)
{
	ADS122C04_Reg.reg0.bit.MUX = mux_config;
	(ADS122C04_writeReg(ADS122C04_CONFIG_0_REG, ADS122C04_Reg.reg0.all));
}

// Configure the gain
void setGain(uint8_t gain_config)
{
	
	ADS122C04_Reg.reg0.bit.GAIN = gain_config;
	(ADS122C04_writeReg(ADS122C04_CONFIG_0_REG, ADS122C04_Reg.reg0.all));
}

// Enable/disable the Programmable Gain Amplifier
void enablePGA(uint8_t enable)
{
	ADS122C04_Reg.reg0.bit.PGA_BYPASS = enable;
	(ADS122C04_writeReg(ADS122C04_CONFIG_0_REG, ADS122C04_Reg.reg0.all));
}

// Set the data rate (sample speed)
void setDataRate(uint8_t rate)
{
	ADS122C04_Reg.reg1.bit.DR = rate;
	(ADS122C04_writeReg(ADS122C04_CONFIG_1_REG, ADS122C04_Reg.reg1.all));
}

// Configure the operating mode (normal / turbo)
void setOperatingMode(uint8_t mode)
{
	ADS122C04_Reg.reg1.bit.MODE = mode;
	(ADS122C04_writeReg(ADS122C04_CONFIG_1_REG, ADS122C04_Reg.reg1.all));
}

// Configure the conversion mode (single-shot / continuous)
void setConversionMode(uint8_t mode)
{
	ADS122C04_Reg.reg1.bit.CMBIT = mode;
	(ADS122C04_writeReg(ADS122C04_CONFIG_1_REG, ADS122C04_Reg.reg1.all));
}

// Configure the voltage reference
void setVoltageReference(uint8_t ref)
{
	ADS122C04_Reg.reg1.bit.VVREF = ref;
	(ADS122C04_writeReg(ADS122C04_CONFIG_1_REG, ADS122C04_Reg.reg1.all));
}

// Enable / disable the internal temperature sensor
void enableInternalTempSensor(uint8_t enable)
{
	
	ADS122C04_Reg.reg1.bit.TS = enable;
	(ADS122C04_writeReg(ADS122C04_CONFIG_1_REG, ADS122C04_Reg.reg1.all));
}

// Enable / disable the conversion data counter
void setDataCounter(uint8_t enable)
{
	
	ADS122C04_Reg.reg2.bit.DCNT = enable;
	(ADS122C04_writeReg(ADS122C04_CONFIG_2_REG, ADS122C04_Reg.reg2.all));
}

// Configure the data integrity check
void setDataIntegrityCheck(uint8_t setting)
{
	ADS122C04_Reg.reg2.bit.CRCbits = setting;
	(ADS122C04_writeReg(ADS122C04_CONFIG_2_REG, ADS122C04_Reg.reg2.all));
}

// Enable / disable the 10uA burn-out current source
void setBurnOutCurrent(uint8_t enable)
{
	ADS122C04_Reg.reg2.bit.BCS = enable;
	(ADS122C04_writeReg(ADS122C04_CONFIG_2_REG, ADS122C04_Reg.reg2.all));
}

// Configure the internal programmable current sources
void setIDACcurrent(uint8_t current)
{
	ADS122C04_Reg.reg2.bit.IDAC = current;
	(ADS122C04_writeReg(ADS122C04_CONFIG_2_REG, ADS122C04_Reg.reg2.all));
}

// Configure the IDAC1 routing
void setIDAC1mux(uint8_t setting)
{
	ADS122C04_Reg.reg3.bit.I1MUX = setting;
	(ADS122C04_writeReg(ADS122C04_CONFIG_3_REG, ADS122C04_Reg.reg3.all));
}

// Configure the IDAC2 routing
void setIDAC2mux(uint8_t setting)
{
	ADS122C04_Reg.reg3.bit.I2MUX = setting;
	(ADS122C04_writeReg(ADS122C04_CONFIG_3_REG, ADS122C04_Reg.reg3.all));
}

// Read Config Reg 2 and check the DRDY bit
// Data is ready when DRDY is high
bool checkDataReady(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_2_REG, &ADS122C04_Reg.reg2.all);
	return(ADS122C04_Reg.reg2.bit.DRDY > 0);
}

// Get the input multiplexer configuration
uint8_t getInputMultiplexer(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_0_REG, &ADS122C04_Reg.reg0.all);
	return(ADS122C04_Reg.reg0.bit.MUX);
}

// Get the gain setting
uint8_t getGain(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_0_REG, &ADS122C04_Reg.reg0.all);
	return(ADS122C04_Reg.reg0.bit.GAIN);
}

// Get the Programmable Gain Amplifier status
uint8_t getPGAstatus(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_0_REG, &ADS122C04_Reg.reg0.all);
	return(ADS122C04_Reg.reg0.bit.PGA_BYPASS);
}

// Get the data rate (sample speed)
uint8_t getDataRate(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_1_REG, &ADS122C04_Reg.reg1.all);
	return(ADS122C04_Reg.reg1.bit.DR);
}

// Get the operating mode (normal / turbo)
uint8_t getOperatingMode(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_1_REG, &ADS122C04_Reg.reg1.all);
	return(ADS122C04_Reg.reg1.bit.MODE);
}
// Get the conversion mode (single-shot / continuous)
uint8_t getConversionMode(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_1_REG, &ADS122C04_Reg.reg1.all);
	return(ADS122C04_Reg.reg1.bit.CMBIT);
}

// Get the voltage reference configuration
uint8_t getVoltageReference(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_1_REG, &ADS122C04_Reg.reg1.all);
	return(ADS122C04_Reg.reg1.bit.VVREF);
}

// Get the internal temperature sensor status
uint8_t getInternalTempSensorStatus(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_1_REG, &ADS122C04_Reg.reg1.all);
	return(ADS122C04_Reg.reg1.bit.TS);
}

// Get the data counter status
uint8_t getDataCounter(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_2_REG, &ADS122C04_Reg.reg2.all);
	return(ADS122C04_Reg.reg2.bit.DCNT);
}

// Get the data integrity check configuration
uint8_t getDataIntegrityCheck(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_2_REG, &ADS122C04_Reg.reg2.all);
	return(ADS122C04_Reg.reg2.bit.CRCbits);
}

// Get the burn-out current status
uint8_t getBurnOutCurrent(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_2_REG, &ADS122C04_Reg.reg2.all);
	return(ADS122C04_Reg.reg2.bit.BCS);
}

// Get the IDAC setting
uint8_t getIDACcurrent(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_2_REG, &ADS122C04_Reg.reg2.all);
	return(ADS122C04_Reg.reg2.bit.IDAC);
}

// Get the IDAC1 mux configuration
uint8_t getIDAC1mux(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_3_REG, &ADS122C04_Reg.reg3.all);
	return(ADS122C04_Reg.reg3.bit.I1MUX);
}

// Get the IDAC2 mux configuration
uint8_t getIDAC2mux(void)
{
	ADS122C04_readReg(ADS122C04_CONFIG_3_REG, &ADS122C04_Reg.reg3.all);
	return(ADS122C04_Reg.reg3.bit.I2MUX);
}


bool write_on_DAC(uint16_t value)
{
	uint8_t lowByte = value & 0x00FF;
	uint8_t highByte = value >> 8;

	start_transmission(DAC8571_ADDR);
	write_on_bus(DAC_control);
	write_on_bus(highByte);
	write_on_bus(lowByte);
	stop_transmission();
	return true;
}

uint16_t DAC_read()
{
	uint8_t highByte = 0;
	uint8_t lowByte  = 0;
    uint8_t control  = 0;  //  not used.

	if (I2C_RawStart(DAC8571_ADDR, I2C_READ))
	{
		I2C_RawStop();
	}

	if (I2C_RawRead(1))
	{
		I2C_RawStop();
	}
	highByte=memdata;
	if (I2C_RawRead(1))
	{
		I2C_RawStop();
	}
	lowByte=memdata;
	if (I2C_RawRead(0))
	{
		I2C_RawStop();
	}
	control=memdata;
	if(control==0)
	{
		
	}
	uint16_t dac_count_value = highByte * 256 + lowByte;
	return dac_count_value;
}

void set_DAC_Percentage(float percentage)
{
	if (percentage < 0) percentage = 0;
	else if (percentage > 100) percentage = 100;
	write_on_DAC(percentage * 655.35);
}


float get_DAC_Percentage()
{
	return DAC_read() * 0.0015259022;  //  === / 655.35;
}

void set_DAC_WriteMode(uint8_t mode)
{
	if (mode > DAC8571_MODE_WRITE_CACHE)
	{
		mode = DAC8571_MODE_NORMAL;
	}
	DAC_control=0x10;
}

uint8_t get_dac_WriteMode()
{
	uint8_t mode = (DAC_control >> 4) & 0x03;
	return mode;
}

void DAC_powerDown(uint8_t pdMode)
{
	uint16_t pdMask = 0x0000;
	//  table 6, page 22.
	switch(pdMode)
	{
		default:
		case DAC8571_PD_LOW_POWER:
		pdMask  = 0x0000;
		break;
		case DAC8571_PD_FAST:
		pdMask  = 0x2000;
		break;
		case DAC8571_PD_1_KOHM:
		pdMask  = 0x4000;
		break;
		case DAC8571_PD_100_KOHM:
		pdMask  = 0x8000;
		break;
		case DAC8571_PD_HI_Z:
		pdMask  = 0xC000;
		break;
	}
	//  specific power down code.
	DAC_control = 0x11;
	write_on_DAC(pdMask);
}

void DAC_wakeUp(uint16_t value)
{
	set_DAC_WriteMode(DAC8571_MODE_NORMAL);
	write_on_DAC(value);
}





void mem_write(unsigned int addr,long int val)
{
	unsigned char r;
	unsigned int s;
	r=val/10000;    //separate out 16bit data for loading
	s=val%10000;// divide by 256 to make 8 bit data//
	eeprom_write_byte((uint8_t*)(1*addr),r); //save on 1st(0x00) loc.of mem
	while(!eeprom_is_ready());
	r=s/256;
	addr=addr+1;
	eeprom_write_byte((uint8_t*)(1*addr),r);
	while(!eeprom_is_ready());
	r=s%256;
	addr=addr+1;
	eeprom_write_byte((uint8_t*)(1*addr),r);
	while(!eeprom_is_ready());
}

long int mem_read( uint8_t addr)
{
	long int o,l;
	unsigned int m,n;
	l=eeprom_read_byte((uint8_t*)(1*addr));
	asm("nop");
	addr=addr+1;
	m=eeprom_read_byte((uint8_t*)(1*addr));
	asm("nop");
	addr=addr+1;
	n=eeprom_read_byte((uint8_t*)(1*addr));
	_delay_ms(30);//20
	o=l*10000+m*256+n;// mul by 256 to recover data
	return (o);
}

void USART0_sendChar(char c)
{
	while (!(USART0.STATUS & USART_DREIF_bm))
	{
		;
	}
	USART0.TXDATAL = c;
}
void USART_0_enable()
{
	USART0.CTRLB |= USART_RXEN_bm | USART_TXEN_bm;
}
void USART_0_disable()
{
	USART0.CTRLB &= ~(USART_RXEN_bm | USART_TXEN_bm);
}
uint8_t USART_0_get_data()
{
	return USART0.RXDATAL;
}

uint8_t USART0_read()
{
	while (!(USART0.STATUS & USART_RXCIF_bm))
	{
		;
	}
	return USART0.RXDATAL;
}


void reply()
{
	USART0_sendChar('O');
	USART0_sendChar('K');
	USART0_sendChar(0x0D);
	strt=0;
	rxcntr=0;
}

void chk_factor()
{
	if(Sensor_Current>0 && Sensor_Current<=100)
	{
		current_factor=0.75;
	}
	if(Sensor_Current>100 && Sensor_Current<=200)
	{
		current_factor=1.20;
	}
	if(Sensor_Current>200 && Sensor_Current<=300)
	{
		current_factor=1.34;
	}
	if(Sensor_Current>300 && Sensor_Current<=400)
	{
		current_factor=1.41;
	}
	if(Sensor_Current>400 && Sensor_Current<=500)
	{
		current_factor=1.454;
	}
	if(Sensor_Current>500 && Sensor_Current<=600)
	{
		current_factor=1.481;
	}
	if(Sensor_Current>600 && Sensor_Current<=700)
	{
		current_factor=1.507;
	}
	if(Sensor_Current>700 && Sensor_Current<=800)
	{
		current_factor=1.5125;
	}
	if(Sensor_Current>800 && Sensor_Current<=900)
	{
		current_factor=1.527;
	}
	if(Sensor_Current>900 && Sensor_Current<=1000)
	{
		current_factor=1.540;
	}
	if(Sensor_Current>1000 && Sensor_Current<=2000)
	{
		current_factor=1.570;
	}
	if(Sensor_Current>2000 && Sensor_Current<=3000)
	{
		current_factor=1.583;
	}
	if(Sensor_Current>3000 && Sensor_Current<=4000)
	{
		current_factor=1.585;
	}
	if(Sensor_Current>4000 && Sensor_Current<=5000)
	{
		current_factor=1.592;
	}
	if(Sensor_Current>5000 && Sensor_Current<=10000)
	{
		current_factor=1.610;
	}
	if(Sensor_Current>10000 && Sensor_Current<=20000)
	{
		current_factor=1.615;
	}
	if(Sensor_Current>20000 && Sensor_Current<=30000)
	{
		current_factor=1.615;
	}
	if(Sensor_Current>30000 && Sensor_Current<=40000)
	{
		current_factor=1.6155;
	}
		
}


void fetch_data()
{
	unsigned char i,j;
	long int store_Val_tx;
	
	
	for(j=1;j<(cal_point+1);j++)
	{
		
			store_data[0]='S';
			store_data[1]='C';
			store_data[2]='P';
			store_data[3]=j+0x30;
			store_data[4]=' ';
			store_Val_tx=calset_value[j];
			store_data[5]=(store_Val_tx/1000)+0x30;
			store_data[6]='.';
			store_data[7]=((store_Val_tx%1000)/100)+0x30;
			store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
			store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
			
			
			for(i=0;i<10;i++)
			{
				USART0_sendChar(store_data[i]); //
			}
			
			USART0_sendChar(0x0D);
	
		
	}
	
	for(j=1;j<(cal_point+1);j++)
	{
		store_data[0]='Z';
		store_data[1]='C';
		store_data[2]='P';
		store_data[3]=j+0x30;
		store_data[4]=' ';

		store_Val_tx=caladc_count[j];
			
		store_data[5]=(store_Val_tx/1000000)+0x30;
		store_data[6]=((store_Val_tx%1000000)/100000)+0x30;
		store_data[7]=(((store_Val_tx%1000000)%100000)/10000)+0x30;
		store_data[8]=((((store_Val_tx%1000000)%100000)%10000)/1000)+0x30;
		store_data[9]='.';
		store_data[10]=(((((store_Val_tx%1000000)%100000)%10000)%1000)/100)+0x30;
		store_data[11]=((((((store_Val_tx%1000000)%100000)%10000)%1000)%100)/10)+0x30;
		store_data[12]=((((((store_Val_tx%1000000)%100000)%10000)%1000)%100)%10)+0x30;
		
		
		for(i=0;i<13;i++)
		{
			USART0_sendChar(store_data[i]); //
		}
		
		USART0_sendChar(0x0D);
	}
	
	
	
	store_Val_tx=Digital_Filter_Value*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='D';
	store_data[1]='F';
	store_data[2]='V';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //Digital_Filter_Value
	}
	
	USART0_sendChar(0x0D);
	
	store_data[0]='A';
	store_data[1]='D';
	store_data[2]='J';
	store_data[3]='=';
	store_data[4]=(Avg_adjust_by/10)+0x30;
	store_data[5]=((Avg_adjust_by%10))+0x30;

	for(i=0;i<6;i++)
	{
		USART0_sendChar(store_data[i]); //H2 Raw Value Adjust by 
	}

	USART0_sendChar(0x0D);
	
	
	store_data[0]='H';
	store_data[1]='S';
	store_data[2]='C';
	store_data[3]='=';
	store_data[4]=(Sensor_Current/10000)+0x30;
	store_data[5]=((Sensor_Current%10000)/1000)+0x30;
	store_data[6]=(((Sensor_Current%10000)%1000)/100)+0x30;
	store_data[7]=((((Sensor_Current%10000)%1000)%100)/10)+0x30;
	store_data[8]=((((Sensor_Current%10000)%1000)%100)%10)+0x30;
	
	for(i=0;i<9;i++)
	{
		USART0_sendChar(store_data[i]); //Threshold
	}
	
	USART0_sendChar(0x0D);
	
	store_data[0]='H';
	store_data[1]='C';
	store_data[2]='D';
	store_data[3]='=';
	store_data[4]=(H2_current_duration/10000)+0x30;
	store_data[5]=((H2_current_duration%10000)/1000)+0x30;
	store_data[6]=(((H2_current_duration%10000)%1000)/100)+0x30;
	store_data[7]=((((H2_current_duration%10000)%1000)%100)/10)+0x30;
	store_data[8]=((((H2_current_duration%10000)%1000)%100)%10)+0x30;
	
	for(i=0;i<9;i++)
	{
		USART0_sendChar(store_data[i]); //H2_current_duration
	}
	
	USART0_sendChar(0x0D);
	
	store_data[0]='S';
	store_data[1]='T';
	store_data[2]='C';
	store_data[3]='=';
	store_data[4]=(Sleep_time_count/10000)+0x30;
	store_data[5]=((Sleep_time_count%10000)/1000)+0x30;
	store_data[6]=(((Sleep_time_count%10000)%1000)/100)+0x30;
	store_data[7]=((((Sleep_time_count%10000)%1000)%100)/10)+0x30;
	store_data[8]=((((Sleep_time_count%10000)%1000)%100)%10)+0x30;
	
	for(i=0;i<9;i++)
	{
		USART0_sendChar(store_data[i]); //Sleep_time_count
	}
	
	USART0_sendChar(0x0D);
	
	store_data[0]='S';
	store_data[1]='M';
	store_data[2]='P';
	store_data[3]='=';
	store_data[4]=(no_sample/10)+0x30;
	store_data[5]=((no_sample%10)/1)+0x30;
	
	for(i=0;i<6;i++)
	{
		USART0_sendChar(store_data[i]); //no_sample
	}
	
	USART0_sendChar(0x0D);

	store_Val_tx=H2_delta_smooth*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='H';
	store_data[1]='D';
	store_data[2]='S';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //H2_delta_smooth
	}
	
	USART0_sendChar(0x0D);
	
		
	store_Val_tx=N2_delta_smooth*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='N';
	store_data[1]='D';
	store_data[2]='S';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //N2_delta_smooth
	}
	
	USART0_sendChar(0x0D);
		
	
	store_data[0]='P';
	store_data[1]='U';
	store_data[2]='L';
	store_data[3]='=';
	store_data[4]=(H2_Pull_Value/10)+0x30;
	store_data[5]=((H2_Pull_Value%10))+0x30;

	for(i=0;i<6;i++)
	{
		USART0_sendChar(store_data[i]); //H2_Pull_Value
	}

	USART0_sendChar(0x0D);
	
	
	
	store_data[0]='A';
	store_data[1]='L';
	store_data[2]='N';
	store_data[3]='=';
	store_data[4]=(Array_length/10)+0x30;
	store_data[5]=((Array_length%10))+0x30;

	for(i=0;i<6;i++)
	{
		USART0_sendChar(store_data[i]); //Array_length
	}

	USART0_sendChar(0x0D);
	
	
	store_data[0]='R';
	store_data[1]='S';
	store_data[2]='T';
	store_data[3]='=';
	store_data[4]=(Run_Sleep_time/10000)+0x30;
	store_data[5]=((Run_Sleep_time%10000)/1000)+0x30;
	store_data[6]=(((Run_Sleep_time%10000)%1000)/100)+0x30;
	store_data[7]=((((Run_Sleep_time%10000)%1000)%100)/10)+0x30;
	store_data[8]=((((Run_Sleep_time%10000)%1000)%100)%10)+0x30;
	
	for(i=0;i<9;i++)
	{
		USART0_sendChar(store_data[i]); //Sleep_time_count
	}
	
	USART0_sendChar(0x0D);
	
	store_Val_tx=Temp_Ramp_Down*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='T';
	store_data[1]='R';
	store_data[2]='D';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //Temp Ramp Down
	}
	
	USART0_sendChar(0x0D);
	
	store_Val_tx=Temp_Ramp_Up*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='T';
	store_data[1]='R';
	store_data[2]='U';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //Temp Ramp Up
	}
	
	USART0_sendChar(0x0D);
	
	store_Val_tx=Temp_Down_Factor*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='T';
	store_data[1]='D';
	store_data[2]='F';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //N2_delta_smooth
	}
	
	USART0_sendChar(0x0D);
	
	store_Val_tx=Temp_Up_Factor*1000;
	
	if(store_Val_tx<0)
	{
		store_data[4]='-';
		store_Val_tx=store_Val_tx*(-1);
	}
	else
	{
		store_data[4]='+';
	}
	store_data[0]='T';
	store_data[1]='U';
	store_data[2]='F';
	store_data[3]='=';
	
	store_data[5]=(store_Val_tx/1000)+0x30;
	store_data[6]='.';
	store_data[7]=((store_Val_tx%1000)/100)+0x30;
	store_data[8]=(((store_Val_tx%1000)%100)/10)+0x30;
	store_data[9]=((((store_Val_tx%1000)%100)%10)/1)+0x30;
	
	
	for(i=0;i<10;i++)
	{
		USART0_sendChar(store_data[i]); //N2_delta_smooth
	}
	
	USART0_sendChar(0x0D);
	
	
		store_data[0]='L';
		store_data[1]='A';
		store_data[2]='P';
		store_data[3]='=';
		store_data[4]=(Low_Alarm/1000)+0x30;
		store_data[5]='.';
		store_data[6]=((Low_Alarm%1000)/100)+0x30;
		store_data[7]=(((Low_Alarm%1000)%100)/10)+0x30;
		store_data[8]=(((Low_Alarm%1000)%100)%10)+0x30;
		
		for(i=0;i<9;i++)
		{
			USART0_sendChar(store_data[i]); //Low ALarm Value
		}
		
		USART0_sendChar(0x0D);
		
		store_data[0]='H';
		store_data[1]='A';
		store_data[2]='P';
		store_data[3]='=';
		store_data[4]=(High_Alarm/1000)+0x30;
		store_data[5]='.';
		store_data[6]=((High_Alarm%1000)/100)+0x30;
		store_data[7]=(((High_Alarm%1000)%100)/10)+0x30;
		store_data[8]=(((High_Alarm%1000)%100)%10)+0x30;
			
		for(i=0;i<9;i++)
		{
			USART0_sendChar(store_data[i]); //High Alarm Value
		}
			
		USART0_sendChar(0x0D);

	// --- NEW CODE ADDED HERE ---
	store_data[0]='S';
	store_data[1]='P';
	store_data[2]='D';
	store_data[3]='=';
	// Fetch the current data rate and convert the hex value (0x0 to 0x6) to an ASCII character
	store_data[4]=getDataRate() + 0x30; 
	
	for(i=0;i<5;i++)
	{
		USART0_sendChar(store_data[i]); // Print Speed Config
	}
	
	USART0_sendChar(0x0D);
	// ---------------------------
				
}



void chk()
{
		long long a,b,c;
		unsigned int i,d,e,f,g,addr;
		char sign;
		i=0;
	    a=0;
		b=0;
		c=0;
		d=0;
	/*	if(company[1]=='F' && company[2]=='A' && company[3]=='C' && company[4]=='T' && company[5]=='O' && company[6]=='R' && company[7]=='Y')
		{
			factory_mode=1;
			reply();
		}*/
		
			
			if(company[1]=='S' && company[2]=='C' && company[3]=='P')// pos 4 space // span calibration point
			{
				cal_point=(company[5]-0x30)*10+(company[6]-0x30);// pos 7 space
				mem_write(0,cal_point);
					for(i=1;i<=cal_point;i++)
					{
						a=(company[8+6*(i-1)]-0x30);
						a=a*1000;
						b=(company[10+6*(i-1)]-0x30);
						b=b*100;
						c=(company[11+6*(i-1)]-0x30);
						c=c*10;
						d=(company[12+6*(i-1)]-0x30);
						d=d*1;
						span_value=a+b+c+d;
						calset_value[i]=span_value;
						//mem_write(20,span_value);
					}
							
				for(i=1;i<=cal_point;i++)
				{
					mem_write((10+(6*(i-1)+3)),calset_value[i]);
				}
				
				reply();
			}
			
			if(company[1]=='Z'&& company[2]=='C' && company[3]=='P')// pos 4 space, 10th place is . like this 0100.250 // Zero calibration point
			{
				cal_point=(company[5]-0x30)*10+(company[6]-0x30);// *ZCP 10 0100.250 0200.350 
				mem_write(0,cal_point);
				
				for(i=1;i<=cal_point;i++)
				{
					a=(company[8+9*(i-1)]-0x30);
					a=a*1000000;
					b=(company[9+9*(i-1)]-0x30);
					b=b*100000;
					c=(company[10+9*(i-1)]-0x30);
					c=c*10000;
					d=(company[11+9*(i-1)]-0x30);
					d=d*1000;
					e=(company[13+9*(i-1)]-0x30);
					e=e*100;
					f= (company[14+9*(i-1)]-0x30);
					f=f*10;
					g= (company[15+9*(i-1)]-0x30)*1;
					
					zero_value=a+b+c+d+e+f+g;
					
					caladc_count[i]=zero_value;
				}
				
				for(i=1;i<=cal_point;i++)
				{
					mem_write((10+6*(i-1)),caladc_count[i]);
					//addr=100+i;
				}
				
				reply();
			}
			
			if(company[1]=='H' && company[2]=='S'  && company[3]=='C' && rxcntr==11 )// *HSC 40000# 5 digit current
			{
				
				Sensor_Current=((company[5]-0x30)*10000)+((company[6]-0x30)*1000)+((company[7]-0x30)*100)+((company[8]-0x30)*10)+(company[9]-0x30);
				
				if(Sensor_Current>45000)
				{
					Sensor_Current=0;
				}
				chk_factor();
				H2_Sensor_Current=float(Sensor_Current)*current_factor;
				reply();
				mem_write((120),Sensor_Current);
			}
		
			if(company[1]=='H' && company[2]=='C'  && company[3]=='D' && rxcntr==11 )// *HCD 00750# 5 digit duration msec
			{
				
				H2_current_duration=((company[5]-0x30)*10000)+((company[6]-0x30)*1000)+((company[7]-0x30)*100)+((company[8]-0x30)*10)+(company[9]-0x30);
				if(H2_current_duration>50000)
				{
					H2_current_duration=1000;
				}
				reply();
				mem_write((125),H2_current_duration);
			}
						
			if(company[1]=='S' && company[2]=='T'  && company[3]=='C' && rxcntr==11 )// *STC 01000# 5 digit duration msec
			{
				
				Sleep_time_count=((company[5]-0x30)*10000)+((company[6]-0x30)*1000)+((company[7]-0x30)*100)+((company[8]-0x30)*10)+(company[9]-0x30);
				if(Sleep_time_count>50000)
				{
					Sleep_time_count=500;
				}
				reply();
				mem_write((130),Sleep_time_count);
			}
			
		    if(company[1]=='S' && company[2]=='M'  && company[3]=='P' && rxcntr==8 )// *SMP 01# 2 digit sample //*SMP 10# 
			{
				
				no_sample=(company[5]-0x30)*10+(company[6]-0x30);
				
				if(no_sample>50)
				{
					no_sample=1;
				}
				reply();
				mem_write((135),no_sample);
			}
			
			if(company[1]=='D' && company[2]=='F'  && company[3]=='V' && rxcntr==12 )//Digital Filter Value *DFV -0.240# 6 digit with sign and decimal
			{
				sign=company[5];
				
				Digital_Filter_Value=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=139;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((140),Digital_Filter_Value);
				
				if(Digital_Filter_Value>9999)
				{
					Digital_Filter_Value=100;
				}
				
				if(sign=='-')
				{
					Digital_Filter_Value=(0-Digital_Filter_Value)/1000;
				}
				else
				{
					Digital_Filter_Value=Digital_Filter_Value/1000;
				}
				
				reply();
			}
			
			if(company[1]=='A' && company[2]=='L'  && company[3]=='N' && rxcntr==8 )//Array Length *ALN 10# 2 digit  
			{
				
				Array_length=(company[5]-0x30)*10+(company[6]-0x30);
				
				if(Array_length>50)
				{
					Array_length=20;
				}
				reply();
				mem_write((145),Array_length);
			}
			
			
			if(company[1]=='A' && company[2]=='D'  && company[3]=='J' && rxcntr==8 )//  *H2 Reference Value in % HRV 50# 2 digit
			{
				
				Avg_adjust_by=(company[5]-0x30)*10+(company[6]-0x30);
				
				if(Avg_adjust_by>99)
				{
					Avg_adjust_by=30;
				}
				reply();
				mem_write((150),Avg_adjust_by);
			}
			
						
			if(company[1]=='H' && company[2]=='D'  && company[3]=='S' && rxcntr==12 )//H2 delta Smooth *HDS -0.100# 6 digit with sign and decimal
			{
				sign=company[5];
				
				H2_delta_smooth=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=154;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((155),H2_delta_smooth);
				
				if(H2_delta_smooth>9999)
				{
					H2_delta_smooth=100;
				}
				
				if(sign=='-')
				{
					H2_delta_smooth=(0-H2_delta_smooth)/1000;
				}
				else
				{
					H2_delta_smooth=H2_delta_smooth/1000;
				}
					
				reply();
			}
			
								
			if(company[1]=='N' && company[2]=='D'  && company[3]=='S' && rxcntr==12 )//N2 delta Smooth *NDS +0.300# 6 digit with sign and decimal
			{
				sign=company[5];
				
				N2_delta_smooth=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=159;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((160),N2_delta_smooth);
					
				if(N2_delta_smooth>9999)
				{
					N2_delta_smooth=300;
				}
					
				if(sign=='-')
				{
					N2_delta_smooth=(0-N2_delta_smooth)/1000;
				}
				else
				{
					N2_delta_smooth=N2_delta_smooth/1000;
				}
					
				reply();
			}
				
			if(company[1]=='T' && company[2]=='R'  && company[3]=='D' && rxcntr==12 )//Temp Ramp Down *TRD +0.300# 6 digit with sign and decimal
			{
				sign=company[5];
				
				Temp_Ramp_Down=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=164;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((165),Temp_Ramp_Down);
						
				if(Temp_Ramp_Down>9999)
				{
					Temp_Ramp_Down=300;
				}
						
				if(sign=='-')
				{
					Temp_Ramp_Down=(0-Temp_Ramp_Down)/1000;
				}
				else
				{
					Temp_Ramp_Down=Temp_Ramp_Down/1000;
				}
						
				reply();
			}
					
			if(company[1]=='T' && company[2]=='R'  && company[3]=='U' && rxcntr==12 )//Temp Ramp Up *TRU +0.300# 6 digit with sign and decimal
			{
				sign=company[5];
				
				Temp_Ramp_Up=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=169;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((170),Temp_Ramp_Up);
							
				if(Temp_Ramp_Up>9999)
				{
					Temp_Ramp_Up=300;
				}
							
				if(sign=='-')
				{
					Temp_Ramp_Up=(0-Temp_Ramp_Up)/1000;
				}
				else
				{
					Temp_Ramp_Up=Temp_Ramp_Up/1000;
				}
							
				reply();
			}
						
			if(company[1]=='T' && company[2]=='D'  && company[3]=='F' && rxcntr==12 )//Temp Down Factor *TDF +0.300# 6 digit with sign and decimal
			{
				sign=company[5];
				
				Temp_Down_Factor=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=174;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((175),Temp_Down_Factor);
							
				if(Temp_Down_Factor>9999)
				{
					Temp_Down_Factor=300;
				}
							
				if(sign=='-')
				{
					Temp_Down_Factor=(0-Temp_Down_Factor)/1000;
				}
				else
				{
					Temp_Down_Factor=Temp_Down_Factor/1000;
				}
							
				reply();
			}
						
			if(company[1]=='T' && company[2]=='U'  && company[3]=='F' && rxcntr==12 )//Temp Up Factor *TUF +0.300# 6 digit with sign and decimal
			{
				sign=company[5];
				
				Temp_Up_Factor=((company[6]-0x30)*1000)+(company[8]-0x30)*100+(company[9]-0x30)*10+(company[10]-0x30);
				
				addr=179;
				eeprom_write_byte((uint8_t*)(1*addr),sign);
				mem_write((180),Temp_Up_Factor);
							
				if(Temp_Up_Factor>9999)
				{
					Temp_Up_Factor=300;
				}
							
				if(sign=='-')
				{
					Temp_Up_Factor=(0-Temp_Up_Factor)/1000;
				}
				else
				{
					Temp_Up_Factor=Temp_Up_Factor/1000;
				}
							
				reply();
			}
						
										
			if(company[1]=='R' && company[2]=='S'  && company[3]=='T' && rxcntr==11 )// *RST 01000# 5 digit duration msec
			{
				
				Run_Sleep_time=((company[5]-0x30)*10000)+((company[6]-0x30)*1000)+((company[7]-0x30)*100)+((company[8]-0x30)*10)+(company[9]-0x30);
				
				if(Run_Sleep_time>50000)
				{
					Run_Sleep_time=200;
				}
				reply();
				mem_write((185),Run_Sleep_time);
			}
						
			
			if(company[1]=='P' && company[2]=='U'  && company[3]=='L' && rxcntr==8 )//  *H2 Pull Value in % PUL 50# 2 digit
			{
				
				H2_Pull_Value=(company[5]-0x30)*10+(company[6]-0x30);
				
				if(H2_Pull_Value>99)
				{
					H2_Pull_Value=50;
				}
				reply();
				mem_write((190),H2_Pull_Value);
			}
			
			if(company[1]=='L' && company[2]=='A' && company[3]=='P' && rxcntr==11 ) // *LAP x.xxx# High Alarm of Sensor 2.000 or 1.000
			{
				
				Low_Alarm=(company[5]-0x30)*1000+(company[7]-0x30)*100+(company[8]-0x30)*10+(company[9]-0x30);
				mem_write(210,Low_Alarm);
				USART0_sendChar('O');
				USART0_sendChar('K');
			}
			
			  if(company[1]=='H' && company[2]=='A' && company[3]=='P' && rxcntr==11 ) // *HAP x.xxx# High Alarm of Sensor 2.000 or 1.000
			  {
				  
				  High_Alarm=(company[5]-0x30)*1000+(company[7]-0x30)*100+(company[8]-0x30)*10+(company[9]-0x30);
				  
				  mem_write(215,High_Alarm);
				  USART0_sendChar('O');
				  USART0_sendChar('K');
			  }
			  
					
				if(company[1]=='F' && company[2]=='A' && company[3]=='C' && company[4]=='T' && company[5]=='O' && company[6]=='R' && company[7]=='Y' )
				{
					factory_mode=1;
					USART0_sendChar('O');
					USART0_sendChar('K');
					strt=0;
					rxcntr=0;
					USART0_sendChar(0x0D);
					fetch_data();
				}
	
}



void update()
{
	if(rxdata=='*')
	{
		strt=1;
		rxcntr=0;
	}
	if(strt==1)
	{
		company[rxcntr]=rxdata;
		rxcntr=rxcntr+1;
		if(rxdata=='#')
		{
			chk();
		}
	}
	
}

ISR(USART0_RXC_vect)
{
	rxdata=USART0.RXDATAL;
	update();
	
}

void USART0_init()
{
	PORTB.DIR &= ~PIN3_bm;//rxd
	PORTB.DIR |= PIN2_bm;// txd
	USART0.BAUD = (uint16_t)USART0_BAUD_RATE(115200); /* set baud rate register to 115200 for fastest output */

	USART0.CTRLA = 0 << USART_ABEIE_bp    /* Auto-baud Error Interrupt Enable: disabled */
	| 0 << USART_DREIE_bp  /* Data Register Empty Interrupt Enable: disabled */
	| 0 << USART_LBME_bp   /* Loop-back Mode Enable: disabled */
	//| 0 << USART_RS485_OFF_gc   /* RS485 Mode disabled */
	| 1 << USART_RXCIE_bp  /* Receive Complete Interrupt Enable: enabled */
	| 0 << USART_RXSIE_bp  /* Receiver Start Frame Interrupt Enable: disabled */
	| 0 << USART_TXCIE_bp; /* Transmit Complete Interrupt Enable: disabled */
	
	USART0.CTRLB |= USART_RXEN_bm | USART_TXEN_bm;
}

void online_tx()
{
	unsigned char i;
	//USART0_sendChar(0x0A); // Optional Line Feed before
	
	for(i=0;i<8;i++)
	{
		USART0_sendChar(str1[i]); // Print Raw Sensor Output / EMF ONLY
	}
	USART0_sendChar(' ');
	for(i=0;i<8;i++){
		USART0_sendChar(str2[i]);
	}
	USART0_sendChar(0x0D); // Carriage Return
	USART0_sendChar(0x0A); // Line Feed
}

// Read the raw signed 24-bit ADC value as int32_t
// The result needs to be multiplied by VREF / GAIN to convert to Volts
int32_t readRawVoltage(uint8_t rate)
{
	raw_voltage_union raw_v; // union to convert uint32_t to int32_t

	bool drdy = false; // DRDY (1 == new data is ready)
	// Start the conversion (assumes we are using single shot mode)
	start();

	
	do 
	{
		_delay_ms(10); // Don't pound the bus too hard
		//millis=millis+1;
		drdy = checkDataReady();
	} while ((drdy == false));

	// Check if we timed out
	if (drdy == false)
	{
		return(0);
	}

	// Read the conversion result
	if(ADS122C04_getConversionData(&raw_v.UINT32) == false)
	{
		return(0);
	}

	// The raw voltage is in the bottom 24 bits of raw_temp
	// If we just do a <<8 we will multiply the result by 256
	// Instead pad out the MSB with the MS bit of the 24 bits
	// to preserve the two's complement
	if ((raw_v.UINT32 & 0x00800000) == 0x00800000)
	raw_v.UINT32 |= 0xFF000000;
	return(raw_v.INT32);
}


void shift_data()
{
	unsigned char j=0;
	//for(j=0;j<(Array_length-1);j++)//5
	for(j=0;j<1;j++)//5
	{
		snsr_avg_data[j]=snsr_avg_data[j+1];
	}
	
}


void shift_temp_data()
{
	unsigned char j=0;
	for(j=0;j<(Array_length-1);j++)//5
	{
		temp_trend_data[j]=temp_trend_data[j+1];
	}
	
}


void plot_data(long data_in)
{
	
	clone[1]=(data_in/1000000)+0x30;
	clone[2]=((data_in%1000000)/100000)+0x30;
	clone[3]=(((data_in%1000000)%100000)/10000)+0x30;
	clone[4]=((((data_in%1000000)%100000)%10000)/1000)+0x30;
	clone[5]='.';
	clone[6]=(((((data_in%1000000)%100000)%10000)%1000)/100)+0x30;
	clone[7]=((((((data_in%1000000)%100000)%10000)%1000)%100)/10)+0x30;
	clone[8]=(((((((data_in%1000000)%100000)%10000)%1000)%100)%10)/1)+0x30;
	
}

double calculate_diff(double data[])
{
	//float sum = 0.0, mean,
	double Sen_Delta = 0.0;
	long dummy_Sen_Delta;
	unsigned char i;
	
	Sen_Delta=data[1]-data[0];//9
	
	dummy_Sen_Delta=Sen_Delta*1000;
	
	if(Sen_Delta>=0.0)
	{
		str3[0]='+';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str3[i]=clone[i];
		}
	}
	else
	{
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
		str3[0]='-';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str3[i]=clone[i];
		}
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
	}
	
	return(Sen_Delta);
}

double calculate_temp_diff(double data[])
{
	//float sum = 0.0, mean,
	double Sen_Delta = 0.0;
	long dummy_Sen_Delta;
	unsigned char i;
	Sen_Delta=data[Array_length-1]-data[5];// take difference with latest array with 5th position
	//Sen_Delta=data[Array_length_actual-1]-data[0];//9
	//Sen_Delta=data[1]-data[0];//9
	
	dummy_Sen_Delta=Sen_Delta*1000;
	
	if(Sen_Delta>=0.0)
	{
		str9[0]='+';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str9[i]=clone[i];
		}
	}
	else
	{
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
		str9[0]='-';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str9[i]=clone[i];
		}
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
	}
	
	return(Sen_Delta);
}


void H2_min_cumu_plot()
{
	long dummy_Sen_Delta;
	unsigned char i;
	dummy_Sen_Delta=H2_min_cumulative*1000;
	
	if(H2_min_cumulative>=0.0)
	{
		str6[0]='+';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str6[i]=clone[i];
		}
	}
	else
	{
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
		str6[0]='-';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str6[i]=clone[i];
		}
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
	}
	
}

void N2_max_cumu_plot()
{
	long dummy_Sen_Delta;
	unsigned char i;
	dummy_Sen_Delta=N2_max_cumulative*1000;
	
	if(N2_max_cumulative>=0.0)
	{
		str7[0]='+';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str7[i]=clone[i];
		}
	}
	else
	{
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
		str7[0]='-';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str7[i]=clone[i];
		}
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
	}
	
}


void Net_cumu_change_plot()
{
	long dummy_Sen_Delta;
	unsigned char i;
	dummy_Sen_Delta=Net_cumu_change*1000;
	
	if(Net_cumu_change>=0.0)
	{
		str8[0]='+';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str8[i]=clone[i];
		}
	}
	else
	{
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
		str8[0]='-';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str8[i]=clone[i];
		}
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
	}
		
}


void Final_Cal_value_plot()
{
	long dummy_Sen_Delta;
	unsigned char i;
	dummy_Sen_Delta=Final_Cal_value*1000;
	
	if(Final_Cal_value>=0.0)
	{
		str10[0]='+';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str10[i]=clone[i];
		}
	}
	else
	{
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
		str10[0]='-';
		plot_data(dummy_Sen_Delta);
		for(i=1;i<9;i++)
		{
			str10[i]=clone[i];
		}
		dummy_Sen_Delta=dummy_Sen_Delta*(-1);
	}
	
}


void adc_read_ch1()// 
{
	long long adc_data,adc_avg;
	unsigned int i;
	uint32_t timeout_counter;
	long dummy_final_cal_value;
	double Sample_difference;
		
	setInputMultiplexer(ADS122C04_MUX_AIN0_AVSS);
	adc_data=0;
	adc_avg=0;
	for(i=0;i<no_sample;i++)//2// adc reading sample
	{
		bool drdy = 0; // DRDY (1 == new data is ready)
		timeout_counter = 0;
		start(); // Start the conversion
		
		do
		{
			drdy = checkDataReady(); // Read DRDY from Config Register 2
			timeout_counter++;
		} while ((drdy == 0) && (timeout_counter < 100000)); // Non-blocking fast loop, no delay_ms()

		// The ADC data is returned in the least-significant 24-bits
		uint32_t raw_ADC_data = readADC();
		float volts = ((float)raw_ADC_data) / 4096;
		adc_data=volts*1000;
		adc_avg=adc_avg+adc_data;
		// Removed _delay_ms(50) bottleneck here for max speed
	}
	
	    adc_data=adc_avg/no_sample;//2
	
		str1[0]=(adc_data/1000000)+0x30;
		str1[1]=((adc_data%1000000)/100000)+0x30;
		str1[2]=(((adc_data%1000000)%100000)/10000)+0x30;
		str1[3]=((((adc_data%1000000)%100000)%10000)/1000)+0x30;
		str1[4]='.';
		str1[5]=(((((adc_data%1000000)%100000)%10000)%1000)/100)+0x30;
		str1[6]=((((((adc_data%1000000)%100000)%10000)%1000)%100)/10)+0x30;
		str1[7]=(((((((adc_data%1000000)%100000)%10000)%1000)%100)%10)/1)+0x30;
	
		
		Raw_Snsr_Mv=double(adc_data)/1000;
		
		if(Ignition_On_Status==0)
		{
			Ignition_off_cycle=Ignition_off_cycle+1;
			
			if(Ignition_off_cycle>13) // on 05/03/2026
			{
				Ignition_off_cycle=11;
			}
		}
		
		//if(Ignition_off_cycle>2)// by this condition we avoid the 2 readings after ignition off, when Ignition off we pull it to zero, but during Ignition On Condition we keep it at 3 so that it will record all the readings
		if(Ignition_off_cycle>10)// by this condition we avoid the 10 readings after ignition off, when Ignition off we pull it to zero, but during Ignition On Condition we keep it at 11 so that it will record all the readings
		{
			
			if(cycle_counter==0)
			{
				Avg_adc_data_Mv=Raw_Snsr_Mv;
			}
			else
			{
				Sample_difference=Raw_Snsr_Mv-Avg_adc_data_Mv;
				
				if(Sample_difference<Digital_Filter_Value)
				{
					Avg_adc_data_Mv=Raw_Snsr_Mv;// direct adc data
				}
				else
				{
					Avg_adc_data_Mv=Avg_adc_data_Mv+(Sample_difference*Avg_adjust_by)/100; 
				}
			}
				
			snsr_avg_data[cycle_counter]=Avg_adc_data_Mv;
			temp_trend_data[temp_cycle_counter]=Avg_adc_data_Mv;
			cycle_counter=cycle_counter+1;	
			temp_cycle_counter=temp_cycle_counter+1;
		
			adc_data=Avg_adc_data_Mv*1000;
	
			str2[0]=(adc_data/1000000)+0x30;
			str2[1]=((adc_data%1000000)/100000)+0x30;
			str2[2]=(((adc_data%1000000)%100000)/10000)+0x30;
			str2[3]=((((adc_data%1000000)%100000)%10000)/1000)+0x30;
			str2[4]='.';
			str2[5]=(((((adc_data%1000000)%100000)%10000)%1000)/100)+0x30;
			str2[6]=((((((adc_data%1000000)%100000)%10000)%1000)%100)/10)+0x30;
			str2[7]=(((((((adc_data%1000000)%100000)%10000)%1000)%100)%10)/1)+0x30;
				
		}
		
		//if(cycle_counter>=Array_length)//11
		if(cycle_counter>=2)//11
		{
			delta_value=calculate_diff(snsr_avg_data);
			
			if(delta_value<H2_delta_smooth)
			{
				H2C=delta_value;
				for(i=0;i<9;i++)
				{
					str4[i]=str3[i];
				}
				
			}
			else
			{
				H2C=0;
				for(i=0;i<9;i++)
				{
					str4[i]='0';
				}
				str4[5]='.';
				str4[0]=' ';
							
			}
			
			if(delta_value>N2_delta_smooth)
			{
				N2C=delta_value;
				for(i=0;i<9;i++)
				{
					str5[i]=str3[i];
				}
				
			}
			else
			{
				N2C=0;
				for(i=0;i<9;i++)
				{
					str5[i]='0';
				}
				str5[5]='.';
				str5[0]=' ';
							
			}
						
							
			if(sesson_end==1)
			{
				H2_min_cumulative=0;
			}
			else
			{
				H2_min_cumulative=H2_min_cumulative+H2C;
			}
			
			H2_min_cumu_plot();
						
			
			if(sesson_end==1)
			{
				N2_max_cumulative=0;
			}
			else
			{
				if(Net_cumu_change==0)
				{
					N2_max_cumulative=0;
				}
				else
				{
					N2_max_cumulative=N2_max_cumulative+N2C;
				}
				
			}
			
			 N2_max_cumu_plot();
			 
			 Net_cumu_change=N2_max_cumulative+H2_min_cumulative;
			 
			 
			 comp_value=(H2_min_cumulative*H2_Pull_Value)/100;//H2_Pull_Value in percentage like 50% 40% etc
			 
			 if(Net_cumu_change>comp_value)
			 {
				 Net_cumu_change=0;
			 }	
			 else
			 {
				 
				 //Net_cumu_change=0-Net_cumu_change;
				 Net_cumu_change=Net_cumu_change;
				 
			 }	
			 
			 Net_cumu_change_plot();
			 
			 if(Prev_Net_cumu_change<0 && Net_cumu_change==0 )
			 {
				 sesson_end=1;		
			 }
			 else
			 {
				 sesson_end=0;
				 
			 }
			 
			 Prev_Net_cumu_change=Net_cumu_change;
			 			 	 			
			shift_data();
			
			cycle_counter=cycle_counter-1;// because we need to match the cycle counter with Interval so that we can calculate the Delta values
			
			if(temp_cycle_counter>=Array_length)
			{
				if(Net_cumu_change==0)
				{
					temp_delta_value=calculate_temp_diff(temp_trend_data);
				}
				else
				{
					temp_delta_value=0;
					for(i=0;i<9;i++)
					{
						str9[i]='0';
					}
					str9[5]='.';
					str9[0]=' ';
				}
				
				if(Ignition_On_Status==1)// if Ignition is On then it compares the temperature effect also other wise remains in stable state
				{
					if(Net_cumu_change==0)
					{
						if(temp_delta_value>Temp_Ramp_Up)
						{
							Temp_status='U';
						}
						else
						{
							if(temp_delta_value<Temp_Ramp_Down)
							{
								Temp_status='D';
							}
							else
							{
								Temp_status='S';
							}
						}
						
					}
				}
				else
				{
					Temp_status='S';// forcefully put into stable state so that it gives Net cumu change value for final calibration points
				}
				
				
				
				
				if(Temp_status=='U')
				{
					Final_Cal_value=Net_cumu_change*Temp_Up_Factor;
				}
				else
				{
					if(Temp_status=='D')
					{
						Final_Cal_value=Net_cumu_change*Temp_Down_Factor;
					}
					else
					{
						Final_Cal_value=Net_cumu_change;
					}
				}
				
				shift_temp_data();
				temp_cycle_counter=temp_cycle_counter-1;// because we need to match the cycle counter with Interval so that we can calculate the Delta values
								
			}
			else
			{
				Final_Cal_value=Net_cumu_change;
			}
			
			
			
			Final_Cal_value=0-Final_Cal_value;// make it positive
			
			Final_Cal_value_plot();
			
			dummy_final_cal_value=Final_Cal_value*1000;
			
			for(poloc=2;(poloc<=cal_point);poloc++)
			{
				if((dummy_final_cal_value<=(caladc_count[poloc])) && (dummy_final_cal_value>(caladc_count[poloc-1])) )// net output
				{
					cal_factor=((float)((caladc_count[poloc])-(caladc_count[poloc-1])))/(float)(calset_value[poloc]-calset_value[poloc-1]);
					h2out=((float(dummy_final_cal_value-(caladc_count[poloc-1])))/cal_factor);
					disp_value= h2out+calset_value[poloc-1];
					
			
				}
				
				if(disp_value>calset_value[cal_point] || dummy_final_cal_value>(caladc_count[cal_point]))
				{
					disp_value=calset_value[cal_point];
					overrange=1;
			
				}
				else
				{
					overrange=0;
				}
		
				if(dummy_final_cal_value<=(caladc_count[1]))
				{
					disp_value=0;
				}
				
				str11[0]=(disp_value/1000)+0x30;
				str11[1]='.';
				str11[2]=((disp_value%1000)/100)+0x30;
				str11[3]=(((disp_value%1000)%100)/10)+0x30;
				str11[4]=((((disp_value%1000)%100)%10)/1)+0x30;
				str11[5]='%';
			
			}
		
	 }
	
	
}

void dac_out(unsigned int DAC_count )
{
	 set_DAC_WriteMode(DAC8571_MODE_NORMAL);
	 //DAC_count=0;// 40000 for 30mA
	 write_on_DAC(DAC_count);
}

void adc_dac_config()
{
	 set_DAC_WriteMode(DAC8571_MODE_NORMAL);
	// setInputMultiplexer(ADS122C04_MUX_AIN0_AIN1); // Route AIN0 and AIN1 to AINP and AINN
	 setInputMultiplexer(ADS122C04_MUX_AIN0_AVSS);
	 setGain(ADS122C04_GAIN_1); // Set the gain to 1
	 enablePGA(ADS122C04_PGA_DISABLED); // Disable the Programmable Gain Amplifier
	 
	 setDataRate(ADS122C04_DATA_RATE_1000SPS); // Yields 2000 SPS when in Turbo Mode
	 setOperatingMode(ADS122C04_OP_MODE_TURBO); // Enable Turbo Mode
	 setConversionMode(ADS122C04_CONVERSION_MODE_CONTINUOUS); // Continuous conversions without start command overhead
	 
	 setVoltageReference(ADS122C04_VREF_INTERNAL); // Use the internal 2.048V reference
	 enableInternalTempSensor(ADS122C04_TEMP_SENSOR_OFF); // Disable the temperature sensor
	 setDataCounter(ADS122C04_DCNT_DISABLE); // Disable the data counter
	 setDataIntegrityCheck(ADS122C04_CRC_DISABLED); // Disable CRC checking
	 setBurnOutCurrent(ADS122C04_BURN_OUT_CURRENT_OFF); // Disable the burn-out current
	 setIDACcurrent(ADS122C04_IDAC_CURRENT_OFF); // Disable the IDAC current
	 setIDAC1mux(ADS122C04_IDAC1_DISABLED); // Disable IDAC1
	 setIDAC2mux(ADS122C04_IDAC2_DISABLED); // Disable IDAC2
}

void int_temp_config()
{
	set_DAC_WriteMode(DAC8571_MODE_NORMAL);
	// setInputMultiplexer(ADS122C04_MUX_AIN0_AIN1); // Route AIN0 and AIN1 to AINP and AINN
	setInputMultiplexer(ADS122C04_MUX_AIN0_AVSS);
	setGain(ADS122C04_GAIN_1); // Set the gain to 1
	enablePGA(ADS122C04_PGA_DISABLED); // Disable the Programmable Gain Amplifier
	
	setDataRate(ADS122C04_DATA_RATE_1000SPS); // Set the data rate to fastest
	setOperatingMode(ADS122C04_OP_MODE_TURBO); // Enable Turbo Mode
	setConversionMode(ADS122C04_CONVERSION_MODE_CONTINUOUS); // Continuous  mode
	
	setVoltageReference(ADS122C04_VREF_INTERNAL); // Use the internal 2.048V reference
	enableInternalTempSensor(ADS122C04_TEMP_SENSOR_ON); // enable the temperature sensor
	setDataCounter(ADS122C04_DCNT_DISABLE); // Disable the data counter
	setDataIntegrityCheck(ADS122C04_CRC_DISABLED); // Disable CRC checking
	setBurnOutCurrent(ADS122C04_BURN_OUT_CURRENT_OFF); // Disable the burn-out current
	setIDACcurrent(ADS122C04_IDAC_CURRENT_OFF); // Disable the IDAC current
	setIDAC1mux(ADS122C04_IDAC1_DISABLED); // Disable IDAC1
	setIDAC2mux(ADS122C04_IDAC2_DISABLED); // Disable IDAC2
}


/*void crc_calculate()
{
	unsigned int checksum;
	checksum=canbustxcrc[0]+canbustxcrc[1]+canbustxcrc[2]+canbustxcrc[3]+canbustxcrc[4]+canbustxcrc[5]+canbustxcrc[6]+(txcounter & 0x0F)+0x0C+0xFF+0x1C+cannewid;
}*/


void run_mode()
{
		unsigned int try_counter,tm,k;
		unsigned int checksum,message_crc;
		
		uint32_t canid_test = 0;
		uint8_t cannewid=0;
		try_counter=0;
		txcounter=0;
		cannewid= mem_read(3);
		struct can_frame canMsg1;
		struct can_frame canMsg;
		MCP2515 mcp2515(20);//10
		canMsg1.can_id  = 0x0CFF1C00 | cannewid ;
		canMsg1.can_dlc = 8;
		canMsg1.data[0] = 0x00;
		canMsg1.data[1] = 0x00;
		canMsg1.data[2] = 0x00;
		canMsg1.data[3] = 0x00;
		canMsg1.data[4] = 0x00;
		canMsg1.data[5] = 0x00;
		canMsg1.data[6] = 0x00;
		canMsg1.data[7] = 0x00;
		mcp2515.reset();
		mcp2515.setBitrate(CAN_500KBPS,MCP_16MHZ); //Sets CAN at speed 500KBPS and Clock 16MHz
		mcp2515.setNormalMode();
		
		/* Disabled CAN receiving check to prevent blockages
		do
		{

			if (mcp2515.readMessage(&canMsg) == MCP2515::ERROR_OK)
			{
				canid_test=0;
				cannewid=0;
				canid_test=canMsg.can_id & 0x0FFF00FF;
				if(canid_test==0x0C1400A3)
				{
					cannewid=(canMsg.can_id & 0x0000FF00)>>8;
					mem_write(3,cannewid);
					canMsg1.can_id=0x0CFF1C00 | cannewid;

				}
			}
			try_counter=try_counter+1;
			_delay_ms(500);
		}while(try_counter<=10);
		*/
		
		 try_counter=0;
		 txcounter=0;
		 adc_dac_config();
		 dac_out(0);		
		
		 while (1)
		 {
			 
// 			 if(!(PORTA.IN & SENSE))
// 			 {
// 				Current_Sleep_time=Run_Sleep_time;
// 				Ignition_On_Status=1;	
// 				Ignition_off_cycle=11;
// 			 }
// 			 else
// 			 {
// 				 Current_Sleep_time=Sleep_time_count;
// 				 Ignition_On_Status=0;
// 			}
            Current_Sleep_time = 0;
			Ignition_On_Status = 1;
			Ignition_off_cycle = 11;
			
// 			if(Pre_Sleep_Time!=Current_Sleep_time)
// 			{
// 				Pre_Sleep_Time=Current_Sleep_time;
// 				for(k=0;k<50;k++)
// 				{
// 					snsr_avg_data[k]=0;
// 					temp_trend_data[k]=0;
// 				}
// 				cycle_counter=0;
// 				temp_cycle_counter=0;
// 				if(Ignition_On_Status==0)// check during ignition Off state and pull down cycle to zero. so that we avoid 2 readings after it.
// 				{
// 					Ignition_off_cycle=0;
// 				}
// 			}
						 
			   dac_out(H2_Sensor_Current);
			   for(tm=0;tm<H2_current_duration;tm++)
			   {
				   _delay_ms(1); // Careful: If H2_current_duration is > 0, this delays your output.
			   }
			  adc_read_ch1();
			  ADC_powerdown();
			   dac_out(0);
			  
			  	if(disp_value>Low_Alarm)// 1.0%
				{
					Low_Alarm_Flag=0x04;// Low Alarm 00000100
				}
				else 
				{
					Low_Alarm_Flag=0x00;// Low Alarm 00000000
				}

				if(disp_value>High_Alarm)// 2.5%
				{
					Hi_Alarm_Flag=0x10;// Hi Alarm 00010000
				}
				else
				{
					Hi_Alarm_Flag=0x00;// Hi Alarm 00000000
				}
			   
			    if(Raw_Snsr_Mv>1900.500 || Raw_Snsr_Mv < 10.000 )// over range data in case sensor burn out or open
				{
					Sensor_Status_Flag=0x01;// sensor error flag 0000001
				}
				else
				{
					Sensor_Status_Flag=0x00;// normal operation
				}
			  
			  Sensor_Status_Byte=( Hi_Alarm_Flag | Low_Alarm_Flag | Sensor_Status_Flag);// According to TATA Motors frame
			  
			  canbustxcrc[2]=Sensor_Status_Byte;//
			  canMsg1.data[2]=Sensor_Status_Byte;//
			  
				canMsg1.data[1]=disp_value/256; // according to Intel format, lower address, least significant byte, higher address most significat byte
				canMsg1.data[0] =disp_value%256;
				canbustxcrc[1]=disp_value/256;
				canbustxcrc[0] =disp_value%256;
				
				 txcounter=txcounter+1;
				 
				 if(txcounter>7)
				 {
					 txcounter=0;
				 }
				 
				 checksum=canbustxcrc[0]+canbustxcrc[1]+canbustxcrc[2]+canbustxcrc[3]+canbustxcrc[4]+canbustxcrc[5]+canbustxcrc[6]+(txcounter & 0x0F)+0x0C+0xFF+0x1C+cannewid;
				 
				 message_crc= (((checksum>>6)&0x03)+(checksum>>3)+checksum) & 0x07;
				 
				 CRC_Counter_Byte=(message_crc<<4) | txcounter;
				 canMsg1.data[3]= CRC_Counter_Byte;
				 
				  PORTA.OUTCLR = SELECT; // Select ON, 
			  
			  	// THE FOLLOWING HAS BEEN COMMENTED OUT.
				// Since no CAN interface is used, this loop was retrying 50 times with a 1ms delay each time, 
				// causing massive bottlenecks when printing via UART.
			    /* 
				do
			  	{
				  	_delay_ms(1);
				  	try_counter=try_counter+1;
			  	} while ((mcp2515.sendMessage(&canMsg1)!= MCP2515::ERROR_OK) && (try_counter<50));
			  	*/
				
				try_counter=0;	
				  
				mcp2515.setSleepMode();	   
				PORTA.OUTSET = SELECT; // Select OFF, // Chip Off in this location then no frames missing 
			    
				online_tx(); // Print EMF value at max speed
				
				for(tm=0;tm<Current_Sleep_time;tm++)// Sleep_time_count
				{
					_delay_ms(1); // Careful: If Current_Sleep_time > 0, this delays your output.
				}
               // mcp2515.reset();
               // mcp2515.setBitrate(CAN_500KBPS,MCP_16MHZ); //Sets CAN at speed 500KBPS and Clock 16MHz
               // mcp2515.setNormalMode();
			   
				
			 			 
		 }
}

int main(void)
{
	
	// UNLOCKED CPU FREQUENCY:
	_PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, 0); // Disable prescaler completely to run at 16 MHz
	_PROTECTED_WRITE(CLKCTRL.MCLKCTRLA, 0); // use internal 16/20MHz oscillator
	while(CLKCTRL.MCLKSTATUS & CLKCTRL_SOSC_bm);// { ; } // wait until clock changed
     unsigned char i,addr;
	 char sign;
	 PORTA.DIRSET=0x00;
	 PORTA.OUTSET=0xF8;
	 PORTB_DIR=0xFF;
	 
	 PORTA.PIN5CTRL |= PORT_PULLUPEN_bm; /* The pull-up configuration */
	 PORTA.DIRSET = SELECT; /* Configure Output for the Select Pin*/
	 PORTA.OUTCLR = SELECT; /* Select on, Hardware set as 1 for On 0 for Off */
	 	
	    SPI0TX_init();
		InitI2C();
		USART0_init();
		//_delay_ms(100);
		sei();
		
		cal_point=mem_read(0);
		if(cal_point>100)
		{
			cal_point=2;
			//mem_write(0,cal_point);
		}
	
		for(i=1;i<(cal_point+1);i++)
		{
			zero_value=mem_read((10+6*(i-1)));
			
		    caladc_count[i]=zero_value;
						
			calset_value[i]=mem_read((10+(6*(i-1)+3)));
		}
		
		Sensor_Current= mem_read(120);
		
		if(Sensor_Current>45000)// 40000(40000uA means 40mA)
		{
			Sensor_Current=0;
		}
		
		chk_factor();
		H2_Sensor_Current=float(Sensor_Current)*current_factor;
		
		H2_current_duration=mem_read(125);
		
		if(H2_current_duration>50000)// 1000 msec
		{
			H2_current_duration=700;
		}
		
		Sleep_time_count=mem_read(130);
		if(Sleep_time_count>50000)
		{
			Sleep_time_count=500;
		}
		
		no_sample=mem_read(135);
		if(no_sample>50)
		{
			no_sample=1;
		}
		
		cycle_counter=0;
		temp_cycle_counter=0;
		addr=139;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
			
		Digital_Filter_Value=mem_read(140);
		
		if(Digital_Filter_Value>9999)
		{
			Digital_Filter_Value=100;
		}
		
		if(sign=='-')
		{
			Digital_Filter_Value=(0-Digital_Filter_Value)/1000;
		}
		else
		{
			Digital_Filter_Value=Digital_Filter_Value/1000;
		}
		
		Array_length=mem_read(145);
		
		if(Array_length>50)
		{
			Array_length=20;
		}
		
		Avg_adjust_by=mem_read(150);
		
		if(Avg_adjust_by>99)
		{
			Avg_adjust_by=30;
		}
		
		//H2_delta_smooth=(-0.100);
		
		addr=154;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
		H2_delta_smooth=mem_read(155);
				
		if(H2_delta_smooth>9999)
		{
			H2_delta_smooth=100;
		}
		
		if(sign=='-')
		{
			H2_delta_smooth=(0-H2_delta_smooth)/1000;
		}
		else
		{
			H2_delta_smooth=H2_delta_smooth/1000;
		}
		
		//N2_delta_smooth=0.300;
		
		addr=159;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
		N2_delta_smooth=mem_read(160);
		
		if(N2_delta_smooth>9999)
		{
			N2_delta_smooth=300;
		}
		
		if(sign=='-')
		{
			N2_delta_smooth=(0-N2_delta_smooth)/1000;
		}
		else
		{
			N2_delta_smooth=N2_delta_smooth/1000;
		}
		
		addr=164;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
		Temp_Ramp_Down=mem_read(165);
		
		if(Temp_Ramp_Down>9999)
		{
			Temp_Ramp_Down=300;
		}
		
		if(sign=='-')
		{
			Temp_Ramp_Down=(0-Temp_Ramp_Down)/1000;
		}
		else
		{
			Temp_Ramp_Down=Temp_Ramp_Down/1000;
		}
		
		addr=169;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
		Temp_Ramp_Up=mem_read(170);
		
		if(Temp_Ramp_Up>9999)
		{
			Temp_Ramp_Up=300;
		}
		
		if(sign=='-')
		{
			Temp_Ramp_Up=(0-Temp_Ramp_Up)/1000;
		}
		else
		{
			Temp_Ramp_Up=Temp_Ramp_Up/1000;
		}
		
		addr=174;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
		Temp_Down_Factor=mem_read(175);
		
		if(Temp_Down_Factor>9999)
		{
			Temp_Down_Factor=300;
		}
		
		if(sign=='-')
		{
			Temp_Down_Factor=(0-Temp_Down_Factor)/1000;
		}
		else
		{
			Temp_Down_Factor=Temp_Down_Factor/1000;
		}
		
		addr=179;
		sign=eeprom_read_byte((uint8_t*)(1*addr));
		asm("nop");
		Temp_Up_Factor=mem_read(180);
		
		if(Temp_Up_Factor>9999)
		{
			Temp_Up_Factor=300;
		}
		
		if(sign=='-')
		{
			Temp_Up_Factor=(0-Temp_Up_Factor)/1000;
		}
		else
		{
			Temp_Up_Factor=Temp_Up_Factor/1000;
		}
						
		Run_Sleep_time=mem_read(185);
		if(Run_Sleep_time>50000)
		{
			Run_Sleep_time=200;
		}
		
				
		H2_Pull_Value=mem_read(190);
		
		if(H2_Pull_Value>99)
		{
			H2_Pull_Value=50;
		}
		
		Low_Alarm=mem_read(210);
		if(Low_Alarm>9999)
		{
			Low_Alarm=1000;
		}
		
		High_Alarm=mem_read(215);
		if(High_Alarm>9999)
		{
			High_Alarm=2500;
		}
			
		Temp_status='S';
		
		run_mode();
   
}