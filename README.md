# e3372-mon
Python script to get statistic from e3372h modem via Telegram

## History
Originally this script was written for a device based on Raspberri Pi, which have access to Internet only via 4G modem e3372h.
Time to time you need to check status of your modem SIM and balance, receive SMS. Due to not all mobile operators provide tools
for remote SIM management (changing tarif plans, check balance, etc.), you need either have static IP for SIM card, bring up VPN
or something else to be able to connect and do this through modem's WEB interface.

To avoid this, we may use such kind of script. Surely, Telegram may be replace with any possible 2-way communication tool.

## Configuration
```
{
	{
		"api_id":		<api-id>,
		"api_hash":		"<api-hash>",
		"session": 		"MySession"
	},
	"telegram-chat-name": "MyChatName",

	"sms-check-period": 60
}
```
`api_id`, `api_hash` - this values may be obtained after you get API key from Telegram. Read more here https://my.telegram.org/apps

`telegram-chat-name` - chat name from where and to which script will interruct (receiving commands, send received SMS)

`sms-check-period` - how often check for new SMS

## Telegram commands
1. Send USSD request - @ussd
For example, to send *100#:
```
@ussd
*100#
```

2. Current month traffic statistics - @stat

## Envinroment
This script is tested under Python 3.8.10.

All necessary packets may be installed through pipenv. 
