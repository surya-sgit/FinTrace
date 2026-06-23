import { processMwrSlicing, MwrSlicingItem } from './LongTermTab';

describe('LongTermTab - processMwrSlicing', () => {
    test('TC3.1: Normal values rendering and sorting order', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'AAPL', standalone_xirr: 0.15, mwr_contribution: 0.05 },
            { ticker: 'MSFT', standalone_xirr: 0.25, mwr_contribution: 0.08 },
            { ticker: 'GOOGL', standalone_xirr: 0.05, mwr_contribution: 0.02 },
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(3);
        // Correct sorting by standalone_xirr descending
        expect(result[0].ticker).toBe('MSFT');
        expect(result[1].ticker).toBe('AAPL');
        expect(result[2].ticker).toBe('GOOGL');

        // Normal values should not be capped
        expect(result[0].standalone_xirr).toBe(0.25);
        expect(result[0].isCapped).toBe(false);
        expect(result[0].original_xirr).toBe(0.25);
    });

    test('TC3.2: Positive outlier capping', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'PENN', standalone_xirr: 50.0, mwr_contribution: 1.0 }, // 5000%
            { ticker: 'AAPL', standalone_xirr: 0.15, mwr_contribution: 0.05 },
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(2);
        expect(result[0].ticker).toBe('PENN');
        // Capped at 10.0 (1000%)
        expect(result[0].standalone_xirr).toBe(10.0);
        expect(result[0].isCapped).toBe(true);
        expect(result[0].original_xirr).toBe(50.0);
    });

    test('TC3.3: Negative outlier capping', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'AAPL', standalone_xirr: 0.15, mwr_contribution: 0.05 },
            { ticker: 'DEAD', standalone_xirr: -5.0, mwr_contribution: -1.0 }, // -500%
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(2);
        expect(result[1].ticker).toBe('DEAD');
        // Capped at -1.0 (-100%)
        expect(result[1].standalone_xirr).toBe(-1.0);
        expect(result[1].isCapped).toBe(true);
        expect(result[1].original_xirr).toBe(-5.0);
    });

    test('TC3.5: Sorting order with mixed outliers and normal values', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'AAPL', standalone_xirr: 0.15, mwr_contribution: 0.05 },
            { ticker: 'PENN', standalone_xirr: 50.0, mwr_contribution: 1.0 },
            { ticker: 'GOOGL', standalone_xirr: 0.25, mwr_contribution: 0.08 },
            { ticker: 'DEAD', standalone_xirr: -5.0, mwr_contribution: -1.0 },
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(4);
        expect(result[0].ticker).toBe('PENN'); // 50.0 (capped at 10.0)
        expect(result[1].ticker).toBe('GOOGL'); // 0.25
        expect(result[2].ticker).toBe('AAPL'); // 0.15
        expect(result[3].ticker).toBe('DEAD'); // -5.0 (capped at -1.0)
    });

    test('TC6.1: Limit boundaries', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'MAX', standalone_xirr: 10.0, mwr_contribution: 1.0 },
            { ticker: 'MIN', standalone_xirr: -1.0, mwr_contribution: -0.1 },
        ];

        const result = processMwrSlicing(input);

        expect(result[0].standalone_xirr).toBe(10.0);
        expect(result[0].isCapped).toBe(false); // Exactly at limit, not capped (or can be true, but not altered)
        expect(result[1].standalone_xirr).toBe(-1.0);
        expect(result[1].isCapped).toBe(false);
    });

    test('TC6.3: NaN, Null, and Undefined values are filtered out', () => {
        const input: any[] = [
            { ticker: 'AAPL', standalone_xirr: 0.15, mwr_contribution: 0.05 },
            { ticker: 'NAN_ASSET', standalone_xirr: NaN, mwr_contribution: 0 },
            { ticker: 'NULL_ASSET', standalone_xirr: null, mwr_contribution: 0 },
            { ticker: 'UNDEF_ASSET', standalone_xirr: undefined, mwr_contribution: 0 },
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(1);
        expect(result[0].ticker).toBe('AAPL');
    });

    test('TC6.4: Close to zero values are preserved', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'SMALL_POS', standalone_xirr: 0.00001, mwr_contribution: 0.0 },
            { ticker: 'SMALL_NEG', standalone_xirr: -0.00001, mwr_contribution: 0.0 },
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(2);
        expect(result[0].standalone_xirr).toBe(0.00001);
        expect(result[1].standalone_xirr).toBe(-0.00001);
    });

    test('TC6.5: All outliers cap to equal max length', () => {
        const input: MwrSlicingItem[] = [
            { ticker: 'OUT1', standalone_xirr: 15.0, mwr_contribution: 1.0 },
            { ticker: 'OUT2', standalone_xirr: 20.0, mwr_contribution: 1.0 },
        ];

        const result = processMwrSlicing(input);

        expect(result).toHaveLength(2);
        expect(result[0].standalone_xirr).toBe(10.0);
        expect(result[0].isCapped).toBe(true);
        expect(result[1].standalone_xirr).toBe(10.0);
        expect(result[1].isCapped).toBe(true);
    });
});
