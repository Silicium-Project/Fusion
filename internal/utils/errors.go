package utils

import "log"

func LogFatal(err error, message string) {
	if err != nil {
		log.Fatalf("%s: %v", message, err)
	}
}
