package com.example.myproject;

import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.yamcs.TmPacket;
import org.yamcs.YConfiguration;
import org.yamcs.tctm.AbstractPacketPreprocessor;
import org.yamcs.utils.TimeEncoding;

/**
 * Component capable of modifying packet binary received from a link, before passing it further into Yamcs.
 * <p>
 * A single instance of this class is created, scoped to the link udp-in.
 * <p>
 * This is specified in the configuration file yamcs.myproject.yaml:
 * 
 * <pre>
 * ...
 * dataLinks:
 *   - name: udp-in
 *     class: org.yamcs.tctm.UdpTmDataLink
 *     stream: tm_realtime
 *     host: localhost
 *     port: 10015
 *     packetPreprocessorClassName: com.example.myproject.MyPacketPreprocessor
 * ...
 * </pre>
 */
public class MyPacketPreprocessor extends AbstractPacketPreprocessor {

    private Map<Integer, AtomicInteger> seqCounts = new HashMap<>();

    // Constructor used when this preprocessor is used without YAML configuration
    public MyPacketPreprocessor(String yamcsInstance) {
        this(yamcsInstance, YConfiguration.emptyConfig());
    }

    // Constructor used when this preprocessor is used with YAML configuration
    // (packetPreprocessorClassArgs)
    public MyPacketPreprocessor(String yamcsInstance, YConfiguration config) {
        super(yamcsInstance, config);
    }

    @Override
    public TmPacket process(TmPacket packet) {
        // Our custom packets don't include a secundary header with time information.
        // Use Yamcs-local time instead.
        packet.setGenerationTime(TimeEncoding.getWallclockTime());

        return packet;
    }
}
