"""Sample before/after snippets used by `skyline demo`, so you can see the
tool work in ten seconds without a git repo."""

PY_BEFORE = '''
class PaymentProcessor:
    def __init__(self, gateway):
        self.gateway = gateway

    def charge(self, amount):
        return self.gateway.send(amount)

    def refund(self, amount):
        return self.gateway.send(-amount)


def validate_amount(amount):
    return amount > 0
'''

PY_AFTER = '''
class BaseProcessor:
    def log(self, msg):
        print(msg)


class PaymentProcessor(BaseProcessor):
    def __init__(self, gateway, retries=3):
        self.gateway = gateway
        self.retries = retries

    def charge(self, amount, currency="USD"):
        return self.gateway.send(amount, currency)

    def refund(self, amount, currency="USD"):
        return self.gateway.send(-amount, currency)

    def status(self, txn_id):
        return self.gateway.status(txn_id)


class RecurringPaymentProcessor(PaymentProcessor):
    def charge_monthly(self, amount):
        return self.charge(amount)


def validate_amount(amount, currency="USD"):
    return amount > 0
'''

TS_BEFORE = '''
interface Gateway {
  send(amount: number): Promise<boolean>;
}

class PaymentProcessor implements Gateway {
  constructor(private apiKey: string) {}

  async send(amount: number): Promise<boolean> {
    return true;
  }

  async refund(amount: number): Promise<boolean> {
    return true;
  }
}

export function validateAmount(amount: number): boolean {
  return amount > 0;
}
'''

TS_AFTER = '''
interface Gateway {
  send(amount: number, currency: string): Promise<boolean>;
  status(txnId: string): Promise<string>;
}

abstract class BaseProcessor {
  protected log(msg: string): void {
    console.log(msg);
  }
}

@Injectable()
class PaymentProcessor extends BaseProcessor implements Gateway {
  private retries: number = 3;

  constructor(private apiKey: string, retries: number = 3) {
    super();
  }

  async send(amount: number, currency: string = "USD"): Promise<boolean> {
    return true;
  }

  async refund(amount: number, currency: string = "USD"): Promise<boolean> {
    return true;
  }

  async status(txnId: string): Promise<string> {
    return "pending";
  }
}

class RecurringPaymentProcessor extends PaymentProcessor {
  async chargeMonthly(amount: number): Promise<boolean> {
    return this.send(amount, "USD");
  }
}

export function validateAmount(amount: number, currency: string = "USD"): boolean {
  return amount > 0;
}
'''
