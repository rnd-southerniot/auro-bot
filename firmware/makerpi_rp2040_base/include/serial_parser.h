#ifndef NAVBOT_SERIAL_PARSER_H
#define NAVBOT_SERIAL_PARSER_H

#include "navbot_protocol.h"

typedef enum navbot_parse_result {
    NAVBOT_PARSE_OK = 0,
    NAVBOT_PARSE_EMPTY,
    NAVBOT_PARSE_UNKNOWN_COMMAND,
    NAVBOT_PARSE_BAD_ARGUMENTS,
    NAVBOT_PARSE_BAD_CHECKSUM,
} navbot_parse_result_t;

navbot_parse_result_t navbot_parse_command_line(const char *line, navbot_command_t *out_command);
const char *navbot_command_name(navbot_command_type_t type);
const char *navbot_parse_result_name(navbot_parse_result_t result);

#endif
