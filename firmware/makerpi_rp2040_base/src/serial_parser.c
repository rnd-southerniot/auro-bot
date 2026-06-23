#include "serial_parser.h"

#include <ctype.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void trim_and_uppercase(const char *src, char *dst, size_t dst_size) {
    size_t start = 0;
    size_t end = strlen(src);

    while (start < end && isspace((unsigned char)src[start])) {
        start++;
    }
    while (end > start && isspace((unsigned char)src[end - 1])) {
        end--;
    }

    size_t len = end - start;
    if (len >= (dst_size - 1)) {
        len = dst_size - 1;
    }

    for (size_t i = 0; i < len; ++i) {
        dst[i] = (char)toupper((unsigned char)src[start + i]);
    }
    dst[len] = '\0';
}

/*
 * Strip and validate an optional *XX checksum suffix.
 *
 * If '*' is found, validate the two-hex-digit XOR checksum against the
 * bytes before '*'. On success, NUL-terminate at '*' (stripping the
 * suffix in place) and return true. On failure, return false.
 *
 * If '*' is not present, the line is accepted as-is (backward compat).
 */
static bool strip_and_validate_checksum(char *line) {
    char *star = strrchr(line, '*');
    if (star == NULL) {
        return true;
    }

    if (strlen(star + 1) != 2) {
        return false;
    }

    char *endptr = NULL;
    unsigned long received = strtoul(star + 1, &endptr, 16);
    if (endptr != star + 3 || received > 0xFF) {
        return false;
    }

    uint8_t expected = navbot_checksum_xor(line, (size_t)(star - line));
    if ((uint8_t)received != expected) {
        return false;
    }

    *star = '\0';
    return true;
}

const char *navbot_command_name(navbot_command_type_t type) {
    switch (type) {
        case NAVBOT_CMD_PING:      return "PING";
        case NAVBOT_CMD_STOP:      return "STOP";
        case NAVBOT_CMD_RESET:     return "RESET";
        case NAVBOT_CMD_ESTOP:     return "ESTOP";
        case NAVBOT_CMD_CMD_VEL:   return "CMD_VEL";
        case NAVBOT_CMD_WHEEL_VEL: return "WHEEL_VEL";
        case NAVBOT_CMD_DIAG:      return "DIAG";
        case NAVBOT_CMD_TEST_PWM:  return "TEST_PWM";
        default:                   return "UNKNOWN";
    }
}

const char *navbot_parse_result_name(navbot_parse_result_t result) {
    switch (result) {
        case NAVBOT_PARSE_OK:              return "OK";
        case NAVBOT_PARSE_EMPTY:           return "EMPTY";
        case NAVBOT_PARSE_UNKNOWN_COMMAND: return "UNKNOWN_COMMAND";
        case NAVBOT_PARSE_BAD_ARGUMENTS:   return "BAD_ARGUMENTS";
        case NAVBOT_PARSE_BAD_CHECKSUM:    return "BAD_CHECKSUM";
        default:                           return "UNKNOWN";
    }
}

navbot_parse_result_t navbot_parse_command_line(const char *line, navbot_command_t *out_command) {
    char buffer[NAVBOT_PROTOCOL_MAX_LINE];
    char extra = '\0';

    if (line == NULL || out_command == NULL) {
        return NAVBOT_PARSE_BAD_ARGUMENTS;
    }

    /* Copy into mutable buffer for checksum stripping. */
    size_t line_len = strlen(line);
    if (line_len >= sizeof(buffer)) {
        line_len = sizeof(buffer) - 1;
    }
    memcpy(buffer, line, line_len);
    buffer[line_len] = '\0';

    /* Strip and validate checksum before any other processing. */
    if (!strip_and_validate_checksum(buffer)) {
        memset(out_command, 0, sizeof(*out_command));
        return NAVBOT_PARSE_BAD_CHECKSUM;
    }

    /* Now trim whitespace and uppercase the payload (checksum stripped). */
    char parsed[NAVBOT_PROTOCOL_MAX_LINE];
    trim_and_uppercase(buffer, parsed, sizeof(parsed));
    if (parsed[0] == '\0') {
        return NAVBOT_PARSE_EMPTY;
    }

    memset(out_command, 0, sizeof(*out_command));
    out_command->type = NAVBOT_CMD_UNKNOWN;

    if (strcmp(parsed, "PING") == 0) {
        out_command->type = NAVBOT_CMD_PING;
        return NAVBOT_PARSE_OK;
    }
    if (strcmp(parsed, "STOP") == 0) {
        out_command->type = NAVBOT_CMD_STOP;
        return NAVBOT_PARSE_OK;
    }
    if (strcmp(parsed, "RESET") == 0) {
        out_command->type = NAVBOT_CMD_RESET;
        return NAVBOT_PARSE_OK;
    }
    if (strcmp(parsed, "ESTOP") == 0) {
        out_command->type = NAVBOT_CMD_ESTOP;
        return NAVBOT_PARSE_OK;
    }
    if (strcmp(parsed, "DIAG") == 0) {
        out_command->type = NAVBOT_CMD_DIAG;
        return NAVBOT_PARSE_OK;
    }
    if (sscanf(parsed, "CMD_VEL %f %f %c", &out_command->value_1, &out_command->value_2, &extra) == 2) {
        if (!isfinite(out_command->value_1) || !isfinite(out_command->value_2)) {
            return NAVBOT_PARSE_BAD_ARGUMENTS;
        }
        out_command->type = NAVBOT_CMD_CMD_VEL;
        return NAVBOT_PARSE_OK;
    }
    if (sscanf(parsed, "WHEEL_VEL %f %f %c", &out_command->value_1, &out_command->value_2, &extra) == 2) {
        if (!isfinite(out_command->value_1) || !isfinite(out_command->value_2)) {
            return NAVBOT_PARSE_BAD_ARGUMENTS;
        }
        out_command->type = NAVBOT_CMD_WHEEL_VEL;
        return NAVBOT_PARSE_OK;
    }
    if (sscanf(parsed, "TEST_PWM %f %f %c", &out_command->value_1, &out_command->value_2, &extra) == 2) {
        if (!isfinite(out_command->value_1) || !isfinite(out_command->value_2)) {
            return NAVBOT_PARSE_BAD_ARGUMENTS;
        }
        out_command->type = NAVBOT_CMD_TEST_PWM;
        return NAVBOT_PARSE_OK;
    }

    if (strncmp(parsed, "CMD_VEL", 7) == 0 ||
        strncmp(parsed, "WHEEL_VEL", 9) == 0 ||
        strncmp(parsed, "TEST_PWM", 8) == 0) {
        return NAVBOT_PARSE_BAD_ARGUMENTS;
    }
    return NAVBOT_PARSE_UNKNOWN_COMMAND;
}
