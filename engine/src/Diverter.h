#pragma once
#include <winsock2.h>
#include <windivert.h>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <unordered_map>
#include <unordered_set>
#include <mutex>
#include <iostream>

class Diverter {
public:
    Diverter();
    ~Diverter();

    bool Start(bool enableTcpSni, bool enableUdpSpoofing, const std::vector<std::string>& allowedProcesses);
    void Stop();

private:
    void WorkerThread();
    void FlowWorkerThread();
    void ProcessPacket(unsigned char* packet, unsigned int packet_len, WINDIVERT_ADDRESS* addr);

    std::string GetProcessNameFromId(DWORD processId);

    bool m_enableTcpSni;
    bool m_enableUdpSpoofing;
    
    HANDLE m_hDevice;
    HANDLE m_hFlowDevice;
    
    std::thread m_worker;
    std::thread m_flowWorker;
    std::atomic<bool> m_running;

    std::unordered_set<std::string> m_allowedProcesses;
    
    // structure mapping (IP, Port) to true (allowed)
    std::unordered_map<uint64_t, bool> m_allowedFlows;
    std::mutex m_flowMutex;

    std::unordered_map<uint32_t, uint16_t> m_udpTracker;
    std::mutex m_trackerMutex;
};
