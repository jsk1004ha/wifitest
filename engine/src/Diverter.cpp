#include "Diverter.h"
#include <iostream>
#include <string>
#include <algorithm>
#include <psapi.h>

Diverter::Diverter() : m_hDevice(INVALID_HANDLE_VALUE), m_hFlowDevice(INVALID_HANDLE_VALUE), m_running(false) {
}

Diverter::~Diverter() {
    Stop();
}

std::string Diverter::GetProcessNameFromId(DWORD processId) {
    std::string processName = "";
    HANDLE hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, FALSE, processId);
    if (hProcess) {
        char buffer[MAX_PATH];
        DWORD size = sizeof(buffer);
        if (QueryFullProcessImageNameA(hProcess, 0, buffer, &size)) {
            processName = buffer;
            size_t pos = processName.find_last_of("\\/");
            if (pos != std::string::npos) {
                processName = processName.substr(pos + 1);
            }
        }
        CloseHandle(hProcess);
    }
    std::transform(processName.begin(), processName.end(), processName.begin(), ::tolower);
    return processName;
}

bool Diverter::Start(bool enableTcpSni, bool enableUdpSpoofing, const std::vector<std::string>& allowedProcesses) {
    if (m_running) return true;
    m_enableTcpSni = enableTcpSni;
    m_enableUdpSpoofing = enableUdpSpoofing;

    m_allowedProcesses.clear();
    for (const auto& proc : allowedProcesses) {
        std::string lowerProc = proc;
        std::transform(lowerProc.begin(), lowerProc.end(), lowerProc.begin(), ::tolower);
        m_allowedProcesses.insert(lowerProc);
    }

    std::string flowFilter = "true";
    m_hFlowDevice = WinDivertOpen(flowFilter.c_str(), WINDIVERT_LAYER_FLOW, 0, WINDIVERT_FLAG_SNIFF | WINDIVERT_FLAG_RECV_ONLY);
    if (m_hFlowDevice == INVALID_HANDLE_VALUE) {
        std::cerr << "Failed to open WinDivert FLOW handle. Error: " << GetLastError() << std::endl;
        return false;
    }

    std::string filter = 
        "(outbound and tcp.DstPort == 443 and tcp.PayloadLength > 0) "
        "or (outbound and udp and udp.DstPort != 53) "
        "or (inbound and udp and udp.DstPort == 53)";

    m_hDevice = WinDivertOpen(filter.c_str(), WINDIVERT_LAYER_NETWORK, 0, 0);
    if (m_hDevice == INVALID_HANDLE_VALUE) {
        WinDivertClose(m_hFlowDevice);
        m_hFlowDevice = INVALID_HANDLE_VALUE;
        std::cerr << "Failed to open WinDivert NETWORK handle. Error: " << GetLastError() << std::endl;
        return false;
    }

    m_running = true;
    m_flowWorker = std::thread(&Diverter::FlowWorkerThread, this);
    m_worker = std::thread(&Diverter::WorkerThread, this);
    std::cout << "Engine started successfully with Process Whitelisting." << std::endl;
    return true;
}

void Diverter::Stop() {
    if (m_running) {
        m_running = false;
        if (m_hDevice != INVALID_HANDLE_VALUE) {
            WinDivertClose(m_hDevice);
            m_hDevice = INVALID_HANDLE_VALUE;
        }
        if (m_hFlowDevice != INVALID_HANDLE_VALUE) {
            WinDivertClose(m_hFlowDevice);
            m_hFlowDevice = INVALID_HANDLE_VALUE;
        }
        if (m_worker.joinable()) m_worker.join();
        if (m_flowWorker.joinable()) m_flowWorker.join();
        std::cout << "Engine stopped." << std::endl;
    }
}

void Diverter::FlowWorkerThread() {
    unsigned char packet[0xFFFF];
    unsigned int packet_len;
    WINDIVERT_ADDRESS addr;

    while (m_running) {
        if (!WinDivertRecv(m_hFlowDevice, packet, sizeof(packet), &packet_len, &addr)) {
            continue;
        }

        if (addr.Event == WINDIVERT_EVENT_FLOW_ESTABLISHED) {
            if (m_allowedProcesses.empty()) continue; // Not tracking specifically, all allowed

            std::string procName = GetProcessNameFromId(addr.Flow.ProcessId);
            if (m_allowedProcesses.count(procName) > 0) {
                // Determine Local IP + Port tuple
                uint32_t addrIP = addr.Flow.LocalAddr[0];
                uint16_t localPort = addr.Flow.LocalPort;
                uint64_t flowKey = ((uint64_t)addrIP << 32) | localPort;
                
                std::lock_guard<std::mutex> lock(m_flowMutex);
                m_allowedFlows[flowKey] = true;
                std::cout << "Whitelisted Flow Matched: " << procName << " (PID: " << addr.Flow.ProcessId << ")\n";
            }
        }
    }
}

void Diverter::WorkerThread() {
    unsigned char packet[0xFFFF];
    unsigned int packet_len;
    WINDIVERT_ADDRESS addr;

    while (m_running) {
        if (!WinDivertRecv(m_hDevice, packet, sizeof(packet), &packet_len, &addr)) {
            continue;
        }
        ProcessPacket(packet, packet_len, &addr);
    }
}

void Diverter::ProcessPacket(unsigned char* packet, unsigned int packet_len, WINDIVERT_ADDRESS* addr) {
    PWINDIVERT_IPHDR ip_header;
    PWINDIVERT_IPV6HDR ipv6_header;
    PWINDIVERT_TCPHDR tcp_header;
    PWINDIVERT_UDPHDR udp_header;
    PVOID payload;
    UINT payload_len;

    WinDivertHelperParsePacket(packet, packet_len, &ip_header, &ipv6_header, NULL, NULL, NULL, &tcp_header, &udp_header, &payload, &payload_len, NULL, NULL);

    // Filter validation check if whitelist is not empty
    if (!m_allowedProcesses.empty()) {
        uint32_t localIP = 0;
        uint16_t localPort = 0;

        if (addr->Outbound) {
            if (ip_header) localIP = ip_header->SrcAddr;
            if (tcp_header) localPort = tcp_header->SrcPort;
            else if (udp_header) localPort = udp_header->SrcPort;
        } else {
            if (ip_header) localIP = ip_header->DstAddr;
            if (tcp_header) localPort = tcp_header->DstPort;
            else if (udp_header) localPort = udp_header->DstPort;
        }

        uint64_t flowKey = ((uint64_t)localIP << 32) | localPort;
        
        bool allowed = false;
        {
            std::lock_guard<std::mutex> lock(m_flowMutex);
            if (m_allowedFlows.count(flowKey) > 0) allowed = true;
        }

        if (!allowed) {
            // Unrecognized flow, just inject it untouched and bypass modifications
            WinDivertSend(m_hDevice, packet, packet_len, NULL, addr);
            return;
        }
    }

    if (tcp_header != NULL && m_enableTcpSni && payload_len > 5 && addr->Outbound) {
        unsigned char* p = (unsigned char*)payload;
        if (p[0] == 0x16 && p[1] == 0x03 && (p[2] == 0x01 || p[2] == 0x03)) {
            unsigned int split_pos = 5;
            unsigned int hdr_len = (unsigned char*)payload - packet;
            
            unsigned char packet1[0xFFFF];
            memcpy(packet1, packet, hdr_len);
            memcpy(packet1 + hdr_len, p, split_pos);
            
            PWINDIVERT_IPHDR ip1 = ip_header ? (PWINDIVERT_IPHDR)(packet1 + ((unsigned char*)ip_header - packet)) : NULL;
            PWINDIVERT_IPV6HDR ipv6_1 = ipv6_header ? (PWINDIVERT_IPV6HDR)(packet1 + ((unsigned char*)ipv6_header - packet)) : NULL;
            
            if (ip1) ip1->Length = htons(ntohs(ip1->Length) - payload_len + split_pos);
            else if (ipv6_1) ipv6_1->Length = htons(ntohs(ipv6_1->Length) - payload_len + split_pos);
            
            WinDivertHelperCalcChecksums(packet1, hdr_len + split_pos, addr, 0);
            WinDivertSend(m_hDevice, packet1, hdr_len + split_pos, NULL, addr);
            
            unsigned char packet2[0xFFFF];
            memcpy(packet2, packet, hdr_len);
            memcpy(packet2 + hdr_len, p + split_pos, payload_len - split_pos);
            
            PWINDIVERT_IPHDR ip2 = ip_header ? (PWINDIVERT_IPHDR)(packet2 + ((unsigned char*)ip_header - packet)) : NULL;
            PWINDIVERT_IPV6HDR ipv6_2 = ipv6_header ? (PWINDIVERT_IPV6HDR)(packet2 + ((unsigned char*)ipv6_header - packet)) : NULL;
            PWINDIVERT_TCPHDR tcp2 = (PWINDIVERT_TCPHDR)(packet2 + ((unsigned char*)tcp_header - packet));
            
            if (ip2) {
                ip2->Length = htons(ntohs(ip2->Length) - split_pos);
                ip2->Id = htons(ntohs(ip2->Id) + 1);
            }
            else if (ipv6_2) {
                ipv6_2->Length = htons(ntohs(ipv6_2->Length) - split_pos);
            }
            
            tcp2->SeqNum = htonl(ntohl(tcp2->SeqNum) + split_pos);
            
            WinDivertHelperCalcChecksums(packet2, hdr_len + payload_len - split_pos, addr, 0);
            WinDivertSend(m_hDevice, packet2, hdr_len + payload_len - split_pos, NULL, addr);
            return; 
        }
    }

    if (udp_header != NULL && m_enableUdpSpoofing && ip_header != NULL) {
        if (addr->Outbound) {
            uint32_t dst_ip = ip_header->DstAddr;
            std::lock_guard<std::mutex> lock(m_trackerMutex);
            m_udpTracker[dst_ip] = udp_header->SrcPort; 
            udp_header->SrcPort = htons(53); 
        } else {
            uint32_t src_ip = ip_header->SrcAddr;
            std::lock_guard<std::mutex> lock(m_trackerMutex);
            auto it = m_udpTracker.find(src_ip);
            if (it != m_udpTracker.end()) {
                udp_header->DstPort = it->second; 
            }
        }
        WinDivertHelperCalcChecksums(packet, packet_len, addr, 0);
    }

    WinDivertSend(m_hDevice, packet, packet_len, NULL, addr);
}
