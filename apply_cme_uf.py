#!/usr/bin/env python3
from pathlib import Path

ROOT = Path("circle-stdlib/libs/circle")

def replace_once(relpath: str, old: str, new: str) -> None:
    path = ROOT / relpath
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{relpath}: expected anchor exactly once, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"patched: {relpath}")

def replace_function(relpath: str, start_marker: str, end_marker: str, new_text: str) -> None:
    path = ROOT / relpath
    text = path.read_text(encoding="utf-8")

    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"{relpath}: start marker not found: {start_marker}")

    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"{relpath}: end marker not found: {end_marker}")

    if text.find(start_marker, start + 1) >= 0:
        raise SystemExit(f"{relpath}: start marker occurs more than once")

    text = text[:start] + new_text.rstrip() + "\n\n" + text[end:]
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"patched function: {relpath}")

replace_once(
    "lib/usb/usbdevicefactory.cpp",
    '''\telse if (   pName->Compare ("int1-3-0") == 0
\t\t || pName->Compare ("ven582-12a") == 0\t\t// Roland UM-ONE MIDI interface
\t\t || pName->Compare ("ven582-28c") == 0)\t\t// Roland JD-08
''',
    '''\telse if (   pName->Compare ("int1-3-0") == 0
\t\t || pName->Compare ("ven582-12a") == 0\t\t// Roland UM-ONE MIDI interface
\t\t || pName->Compare ("ven582-28c") == 0\t\t// Roland JD-08
\t\t || pName->Compare ("ven7104-2202") == 0)\t// CME UF5/UF6/UF7/UF8
'''
)

replace_once(
    "lib/usb/usbmidihost.cpp",
    '''\tboolean bIsRoland =    pDeviceDesc->idVendor == 0x0582
\t\t\t    && (   pDeviceDesc->idProduct == 0x012A
\t\t\t        || pDeviceDesc->idProduct == 0x028C);
''',
    '''\tboolean bIsRoland =    pDeviceDesc->idVendor == 0x0582
\t\t\t    && (   pDeviceDesc->idProduct == 0x012A
\t\t\t        || pDeviceDesc->idProduct == 0x028C);
\tboolean bIsCMEUF =     pDeviceDesc->idVendor  == 0x7104
\t\t\t    && pDeviceDesc->idProduct == 0x2202;
'''
)

replace_once(
    "lib/usb/usbmidihost.cpp",
    '''\t\tif (!bIsRoland)
''',
    '''\t\tif (!bIsRoland && !bIsCMEUF)
'''
)

new_completion = r'''void CUSBMIDIHostDevice::CompletionRoutine (CUSBRequest *pURB)
{
	assert (pURB != 0);
	assert (m_pInterface != 0);

	boolean bRestart = FALSE;
	if (pURB->GetStatus () != 0)
	{
		assert (m_pPacketBuffer != 0);

		const TUSBDeviceDescriptor *pDeviceDesc = GetDevice ()->GetDeviceDescriptor ();
		assert (pDeviceDesc != 0);
		boolean bIsCMEUF =     pDeviceDesc->idVendor  == 0x7104
				    && pDeviceDesc->idProduct == 0x2202;

		if (bIsCMEUF)
		{
			u8 *pBuffer = m_pPacketBuffer;
			unsigned nRemaining = pURB->GetResultLength ();

			while (nRemaining >= CUSBMIDIDevice::EventPacketSize)
			{
				unsigned nSourceLength = CUSBMIDIDevice::EventPacketSize;

				if ((pBuffer[0] & 0x0F) == 0x0F)
				{
					unsigned nDataLength = 1;

					if (pBuffer[1] == 0xF0)
					{
						u8 *pEOX = pBuffer + 2;
						unsigned nSearchLength = nRemaining - 2;

						while (nSearchLength > 1 && *pEOX != 0xF7)
						{
							pEOX++;
							nSearchLength--;
						}

						nDataLength = (unsigned) (pEOX - pBuffer);
						nSourceLength = nDataLength + 1;
					}
					else if (pBuffer[1] == 0xF2)
					{
						nDataLength = 3;
					}

					unsigned nCable = pBuffer[0] >> 4;

					if (pBuffer[1] == 0xF0)
					{
						unsigned nOffset = 0;
						while (nOffset < nDataLength)
						{
							unsigned nBytes = nDataLength - nOffset;
							if (nBytes > 3)
							{
								nBytes = 3;
							}

							u8 Packet[CUSBMIDIDevice::EventPacketSize] = {0, 0, 0, 0};

							if (nOffset + nBytes < nDataLength)
							{
								Packet[0] = (u8) ((nCable << 4) | 0x04);
							}
							else
							{
								Packet[0] = (u8) ((nCable << 4) | (nBytes + 4));
							}

							memcpy (&Packet[1], &pBuffer[1 + nOffset], nBytes);

							if (m_pInterface->CallPacketHandler (
								Packet, CUSBMIDIDevice::EventPacketSize))
							{
								bRestart = TRUE;
							}

							nOffset += nBytes;
						}
					}
					else
					{
						u8 Packet[CUSBMIDIDevice::EventPacketSize] = {0, 0, 0, 0};
						unsigned nCIN = pBuffer[1] == 0xF2 ? 0x03 : 0x0F;

						Packet[0] = (u8) ((nCable << 4) | nCIN);
						memcpy (&Packet[1], &pBuffer[1], nDataLength);

						if (m_pInterface->CallPacketHandler (
							Packet, CUSBMIDIDevice::EventPacketSize))
						{
							bRestart = TRUE;
						}
					}
				}
				else
				{
					if (m_pInterface->CallPacketHandler (
						pBuffer, CUSBMIDIDevice::EventPacketSize))
					{
						bRestart = TRUE;
					}
				}

				pBuffer += nSourceLength;
				nRemaining -= nSourceLength;
			}
		}
		else if (pURB->GetResultLength () % CUSBMIDIDevice::EventPacketSize == 0)
		{
			bRestart = m_pInterface->CallPacketHandler (m_pPacketBuffer,
								    pURB->GetResultLength ());
		}
	}
	else if (   m_pInterface->GetAllSoundOffOnUSBError ()
		 && !pURB->GetStatus ()
		 && pURB->GetUSBError () != USBErrorUnknown)
	{
		for (u8 nChannel = 0; nChannel < 16; nChannel++)
		{
			u8 AllSoundOff[] = {0x0B, (u8) (0xB0 | nChannel), 120, 0};
			m_pInterface->CallPacketHandler (AllSoundOff,  sizeof AllSoundOff);
		}
	}

	delete pURB;
	if (   bRestart
	    || CKernelOptions::Get ()->GetUSBBoost ())
	{
		StartRequest ();
	}
	else
	{
		assert (m_hTimer == 0);
		m_hTimer = CTimer::Get ()->StartKernelTimer (MSEC2HZ (10), TimerStub, 0, this);
		assert (m_hTimer != 0);
	}
}'''

replace_function(
    "lib/usb/usbmidihost.cpp",
    "void CUSBMIDIHostDevice::CompletionRoutine (CUSBRequest *pURB)",
    "void CUSBMIDIHostDevice::CompletionStub (CUSBRequest *pURB, void *pParam, void *pContext)",
    new_completion
)

print("CME UF USB-MIDI compatibility changes applied successfully.")
